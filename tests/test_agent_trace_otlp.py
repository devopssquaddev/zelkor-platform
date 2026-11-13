"""A wrapped agent's run is one OTLP waterfall: agent root -> sidecar chat -> gateway chat (live).

The OTLP counterpart of the Langfuse waterfall test, for installs that export to a collector
(profile=perimeter, or full with Langfuse off). Needs KUBECONTEXT, ZELKOR_RUNTIME_GRAPHS, a
tenant token, a platform contract with OTLP_RELAY_SERVICE, and ZELKOR_OTLP_SINK=<namespace>/
<deployment> naming a collector whose `debug` exporter (verbosity normal) logs the spans it
receives. Skips otherwise.
"""
from __future__ import annotations

import os
import re
import time
import uuid

import pytest

from tests.helpers.kube import kubectl_run, platform_contract
from tests.helpers.runtime_agents import require_kube, run, runtime_graphs, tenant_id, tenant_token

# debug exporter (normal): "<span name> <trace id> <span id> key=value ...", the first span of a
# batch prefixed with "<timestamp>\tinfo\t".
SPAN = re.compile(r"(?:^|\t)(?P<name>[^\t]+?) (?P<trace>[0-9a-f]{32}) (?P<span>[0-9a-f]{16})(?P<attrs>.*)$")


def _attr(attrs: str, key: str) -> str:
    m = re.search(rf"(?:^| ){re.escape(key)}=(\S+)", attrs)
    return m.group(1) if m else ""


def _sink() -> tuple[str, str]:
    sink = os.environ.get("ZELKOR_OTLP_SINK", "").strip()
    if "/" not in sink:
        pytest.skip("ZELKOR_OTLP_SINK=<namespace>/<deployment> not set (collector with a debug exporter)")
    ns, deploy = sink.split("/", 1)
    return ns, deploy


def _spans(ns: str, deploy: str) -> list[dict]:
    res = kubectl_run(["logs", f"deploy/{deploy}", "--since=3m"], namespace=ns, timeout=60)
    assert res.returncode == 0, res.stderr
    spans = []
    for line in res.stdout.splitlines():
        m = SPAN.search(line)
        if m:
            spans.append({"name": m["name"].strip(), "trace": m["trace"], "attrs": m["attrs"]})
    return spans


def test_wrapped_run_is_one_waterfall_in_the_collector():
    require_kube()
    ns, deploy = _sink()
    if not platform_contract(os.environ.get("ZELKOR_PLATFORM_NAMESPACE", "zelkor")).get("OTLP_RELAY_SERVICE"):
        pytest.skip("platform exports no OTLP (contract has no OTLP_RELAY_SERVICE)")
    graph = runtime_graphs()[0]
    token = tenant_token("tenant-a")
    thread, _ = run(graph, token, f"Reply with one word: ok ({uuid.uuid4().hex[:8]})")

    deadline = time.monotonic() + 60
    trace: list[dict] = []
    while time.monotonic() < deadline:
        spans = _spans(ns, deploy)
        roots = [s for s in spans if s["name"] == graph and _attr(s["attrs"], "session.id") == thread]
        if roots:
            trace = [s for s in spans if s["trace"] == roots[0]["trace"]]
            if sum(_attr(s["attrs"], "gen_ai.operation.name") == "chat" for s in trace) >= 2:
                break
        time.sleep(3)
    assert trace, f"no {graph} root span with session.id={thread} reached the collector"
    (root,) = [s for s in trace if s["name"] == graph]
    assert _attr(root["attrs"], "user.id") == tenant_id(token)
    chats = [s for s in trace if _attr(s["attrs"], "gen_ai.operation.name") == "chat"]
    # the sidecar's chat span and the gateway's chat span join the agent's trace (traceparent)
    assert len(chats) >= 2, [s["name"] for s in trace]
    assert any(_attr(s["attrs"], "gen_ai.provider.name") for s in chats), "no gateway chat span in the trace"
