"""A wrapped agent's run is one OTLP waterfall: agent root -> sidecar chat -> gateway chat (live).

The OTLP counterpart of the Langfuse waterfall test, for installs that export to a collector
(profile=perimeter, or full with Langfuse off). Needs KUBECONTEXT, ZELKOR_RUNTIME_GRAPHS, a
tenant token, a platform contract with OTLP_RELAY_SERVICE, and ZELKOR_OTLP_SINK (see
tests/helpers/otlp_sink.py). With ZELKOR_OTLP_EXPORTER set, the collector must also have
forwarded the spans to its backend without a send failure. Skips otherwise.
"""
from __future__ import annotations

import os
import time
import uuid

import pytest

from tests.helpers import otlp_sink
from tests.helpers.kube import platform_contract
from tests.helpers.runtime_agents import require_kube, run, tenant_id, tenant_token

GRAPHS = [g.strip() for g in os.environ.get("ZELKOR_RUNTIME_GRAPHS", "").split(",") if g.strip()] or [""]


def _require_otlp() -> None:
    require_kube()
    otlp_sink.sink()
    if not platform_contract(os.environ.get("ZELKOR_PLATFORM_NAMESPACE", "zelkor")).get("OTLP_RELAY_SERVICE"):
        pytest.skip("platform exports no OTLP (contract has no OTLP_RELAY_SERVICE)")


@pytest.mark.parametrize("graph", GRAPHS)
def test_wrapped_run_is_one_waterfall_in_the_collector(graph):
    if not graph:
        pytest.skip("ZELKOR_RUNTIME_GRAPHS not set")
    _require_otlp()
    token = tenant_token("tenant-a")
    thread, _ = run(graph, token, f"Reply with one word: ok ({uuid.uuid4().hex[:8]})")

    trace = otlp_sink.trace_for_session(graph, thread)
    assert trace, f"no {graph} root span with session.id={thread} reached the collector"
    (root,) = [s for s in trace if s["name"] == graph]
    assert otlp_sink.attr(root, "user.id") == tenant_id(token)
    chats = [s for s in trace if otlp_sink.attr(s, "gen_ai.operation.name") == "chat"]
    # the sidecar's chat span and the gateway's chat span join the agent's trace (traceparent)
    assert len(chats) >= 2, [s["name"] for s in trace]
    assert any(otlp_sink.attr(s, "gen_ai.provider.name") for s in chats), "no gateway chat span in the trace"
    print(f"{graph} trace_id={root['trace']} session.id={thread}")


def test_collector_forwards_run_spans_to_its_backend():
    """The debug log proves receipt; the backend exporter's counters prove delivery."""
    if not GRAPHS[0]:
        pytest.skip("ZELKOR_RUNTIME_GRAPHS not set")
    _require_otlp()
    sent0, failed0 = otlp_sink.exporter_counts()
    thread, _ = run(GRAPHS[0], tenant_token("tenant-a"), f"Reply with one word: ok ({uuid.uuid4().hex[:8]})")
    assert otlp_sink.trace_for_session(GRAPHS[0], thread), "run never reached the collector"
    deadline = time.monotonic() + 60  # batch processor flushes within seconds
    sent, failed = sent0, failed0
    while time.monotonic() < deadline and sent <= sent0:
        time.sleep(5)
        sent, failed = otlp_sink.exporter_counts()
    assert sent > sent0, "collector received the run but its backend exporter sent no spans"
    assert failed == failed0, f"backend exporter failed {failed - failed0} spans"
