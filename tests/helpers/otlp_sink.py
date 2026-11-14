"""Live helpers for an OTLP collector sink (installs that export traces instead of Langfuse).

Env (tests skip without them):
  ZELKOR_OTLP_SINK      <namespace>/<deployment> of a collector whose `debug` exporter
                        (verbosity normal) logs the spans it receives
  ZELKOR_OTLP_EXPORTER  optional: the collector exporter that forwards to the real backend
                        (e.g. otlphttp/google); its internal metrics (:8888) prove delivery
"""
from __future__ import annotations

import json
import os
import re
import time

import pytest

from tests.helpers.kube import kubectl_run

# debug exporter (normal): "<span name> <trace id> <span id> key=value ...", the first span of a
# batch prefixed with "<timestamp>\tinfo\t".
SPAN = re.compile(r"(?:^|\t)(?P<name>[^\t]+?) (?P<trace>[0-9a-f]{32}) (?P<span>[0-9a-f]{16})(?P<attrs>.*)$")


def attr(span: dict, key: str) -> str:
    m = re.search(rf"(?:^| ){re.escape(key)}=(\S+)", span["attrs"])
    return m.group(1) if m else ""


def sink() -> tuple[str, str]:
    value = os.environ.get("ZELKOR_OTLP_SINK", "").strip()
    if "/" not in value:
        pytest.skip("ZELKOR_OTLP_SINK=<namespace>/<deployment> not set (collector with a debug exporter)")
    ns, deploy = value.split("/", 1)
    return ns, deploy


def spans(since: str = "5m") -> list[dict]:
    ns, deploy = sink()
    res = kubectl_run(["logs", f"deploy/{deploy}", f"--since={since}"], namespace=ns, timeout=60)
    assert res.returncode == 0, res.stderr
    out = []
    for line in res.stdout.splitlines():
        m = SPAN.search(line)
        if m:
            out.append({"name": m["name"].strip(), "trace": m["trace"], "span": m["span"], "attrs": m["attrs"]})
    return out


def trace_for_session(graph: str, thread: str, *, want: int = 2, want_tool: str = "",
                      timeout: float = 90.0) -> list[dict]:
    """Spans of the trace whose `graph` root carries session.id=thread, once `want` chat spans
    (and a tool span for `want_tool`, if set) have landed."""
    deadline = time.monotonic() + timeout
    trace: list[dict] = []
    while time.monotonic() < deadline:
        all_spans = spans()
        roots = [s for s in all_spans if s["name"] == graph and attr(s, "session.id") == thread]
        if roots:
            trace = [s for s in all_spans if s["trace"] == roots[0]["trace"]]
            chats = sum(attr(s, "gen_ai.operation.name") == "chat" for s in trace)
            tool_ok = not want_tool or any(attr(s, "gen_ai.tool.name") == want_tool for s in trace)
            if chats >= want and tool_ok:
                return trace
        time.sleep(3)
    return trace


def exporter_counts() -> tuple[float, float]:
    """(sent, failed) span counters of ZELKOR_OTLP_EXPORTER from the collector's :8888 metrics."""
    exporter = os.environ.get("ZELKOR_OTLP_EXPORTER", "").strip()
    if not exporter:
        pytest.skip("ZELKOR_OTLP_EXPORTER not set (backend exporter of the collector)")
    ns, deploy = sink()
    sel = kubectl_run(["get", "deploy", deploy, "-o", "jsonpath={.spec.selector.matchLabels}"], namespace=ns)
    assert sel.returncode == 0, sel.stderr
    labels = ",".join(f"{k}={v}" for k, v in json.loads(sel.stdout).items())
    pod = kubectl_run(["get", "pods", "-l", labels, "--field-selector=status.phase=Running",
                       "-o", "jsonpath={.items[0].metadata.name}"], namespace=ns)
    assert pod.returncode == 0 and pod.stdout, pod.stderr
    raw = kubectl_run(["get", "--raw", f"/api/v1/namespaces/{ns}/pods/{pod.stdout}:8888/proxy/metrics"],
                      namespace=ns, timeout=30)
    assert raw.returncode == 0, f"collector :8888 metrics unreachable: {raw.stderr}"

    def total(metric: str) -> float:
        pat = re.compile(rf'^otelcol_exporter_{metric}_spans(?:_total)?\{{[^}}]*exporter="{re.escape(exporter)}"[^}}]*\}} (\S+)$')
        return sum(float(m.group(1)) for line in raw.stdout.splitlines() if (m := pat.match(line)))

    return total("sent"), total("send_failed")
