"""UAT-24: non-Aegra runtime agents run governed (live; skips without ZELKOR_RUNTIME_GRAPHS).

Pair with ``AEGRA_WORKER_GRAPH_ID=<graph> pytest tests/test_drop_in_langgraph_sdk.py`` per graph.
"""
from __future__ import annotations

import json

import os

import pytest

from tests.helpers import otlp_sink
from tests.helpers.kube import kubectl_run, platform_contract
from tests.helpers.runtime_agents import (
    BENIGN_PROMPT, ESCAPE_PROMPT, REFUSAL, error_spans, final_text, require_kube, run, run_error, runtime_graphs,
    sandbox_execution_metadata, sandbox_run, tenant_id, tenant_token, tool_spans, trace_for_thread,
)


def _graphs():
    try:
        return runtime_graphs()
    except pytest.skip.Exception:
        return []


def _contract() -> dict:
    return platform_contract(os.environ.get("ZELKOR_PLATFORM_NAMESPACE", "zelkor"))


@pytest.fixture
def langfuse_platform():
    """The Langfuse-trace cases need bundled Langfuse; an OTLP-only platform runs the OTLP case."""
    if _contract().get("OTLP_RELAY_SERVICE"):
        pytest.skip("platform exports traces to an OTLP collector (see the _otlp case)")


@pytest.mark.parametrize("graph", _graphs() or [pytest.param("-", marks=pytest.mark.skip("ZELKOR_RUNTIME_GRAPHS not set"))])
def test_uat24_sandbox_run_is_one_governed_trace(graph, langfuse_platform):
    token = tenant_token("tenant-a")
    full, sandbox = sandbox_run(graph, token)
    roots = {str(o.get("name")) for o in full if not o.get("parentObservationId")}
    users = {o.get("userId") for o in full if o.get("userId")}
    assert roots == {graph}, roots
    assert users == {tenant_id(token)}, users
    assert len({o.get("traceId") for o in full}) == 1
    assert any(str(o.get("type")).upper() == "GENERATION" for o in full), "no LLM generation in the run trace"
    assert sandbox and sandbox.get("outcome") == "denied", sandbox
    assert error_spans(full) == [], error_spans(full)


@pytest.mark.parametrize("graph", _graphs() or [pytest.param("-", marks=pytest.mark.skip("ZELKOR_RUNTIME_GRAPHS not set"))])
def test_uat24_benign_code_runs_in_sandbox(graph, langfuse_platform):
    """A plain calculation is not refused, runs in the sandbox (outcome=allowed), and its output is the reply."""
    token = tenant_token("tenant-a")
    full: list[dict] = []
    text = ""
    for _ in range(3):  # retry only when the model skips the tool; a refusal fails at once
        thread, out = run(graph, token, BENIGN_PROMPT)
        assert run_error(out) is None, run_error(out)
        text = final_text(out)
        assert REFUSAL not in text, f"{graph}: rail refused benign code"
        full = trace_for_thread(thread, graph=graph, want_tool=True)
        if tool_spans(full):
            break
    assert tool_spans(full), f"{graph}: model never called sandbox__execute_python"
    sandbox = sandbox_execution_metadata(full)
    assert sandbox and sandbox.get("outcome") == "allowed", sandbox
    assert "45" in text, text[:300]
    assert error_spans(full) == [], error_spans(full)


@pytest.mark.parametrize("graph", _graphs() or [pytest.param("-", marks=pytest.mark.skip("ZELKOR_RUNTIME_GRAPHS not set"))])
def test_uat24_escape_attempt_is_stopped_by_rail_or_sandbox(graph, langfuse_platform):
    """Defense in depth: NeMo refuses the mknod request, or the sandbox denies and stamps it."""
    thread, out = run(graph, tenant_token("tenant-a"), ESCAPE_PROMPT)
    assert run_error(out) is None, run_error(out)
    if REFUSAL in final_text(out):
        return
    full = trace_for_thread(thread, graph=graph, want_tool=True)
    assert tool_spans(full), "not refused by NeMo and no sandbox call"
    sandbox = sandbox_execution_metadata(full)
    assert sandbox and sandbox.get("violation") == "permission_denied_mknod", sandbox


@pytest.mark.parametrize("graph", _graphs() or [pytest.param("-", marks=pytest.mark.skip("ZELKOR_RUNTIME_GRAPHS not set"))])
def test_uat24_agent_container_has_no_datastore_credentials(graph):
    require_kube()
    proc = kubectl_run(["get", f"deploy/{graph}-zelkor-agent", "-o", "json"])
    assert proc.returncode == 0, proc.stderr
    pod = json.loads(proc.stdout)["spec"]["template"]["spec"]
    agent = next(c for c in pod["containers"] if c["name"] == "agent")
    env = {e["name"] for e in agent.get("env") or []}
    assert not env & {"DATABASE_URL", "REDIS_URL", "VALKEY_URL"}, env
    assert not any("secretRef" in (f or {}) for f in agent.get("envFrom") or []), agent.get("envFrom")
    sc = agent.get("securityContext") or {}
    assert sc.get("readOnlyRootFilesystem") is True, sc
    assert sc.get("allowPrivilegeEscalation") is False, sc


def test_uat24_byo_a2a_image_is_governed_like_ours():
    """A customer image serving A2A on 127.0.0.1:8080 (`zelkor deploy --runtime a2a` + own Dockerfile)."""
    import os

    graph = os.environ.get("BYO_A2A_GRAPH", "").strip()
    if not graph:
        pytest.skip("BYO_A2A_GRAPH not set")
    test_uat24_sandbox_run_is_one_governed_trace(graph, None)
    test_uat24_agent_container_has_no_datastore_credentials(graph)


@pytest.mark.parametrize("graph", _graphs() or [pytest.param("-", marks=pytest.mark.skip("ZELKOR_RUNTIME_GRAPHS not set"))])
def test_uat24_benign_code_runs_in_sandbox_otlp(graph):
    """OTLP platforms (e.g. perimeter with perimeter.sandbox): the same benign run, read from the
    collector: one trace with the sandbox tool span, outcome=allowed, no failed span."""
    require_kube()
    contract = _contract()
    if not contract.get("OTLP_RELAY_SERVICE") or contract.get("SANDBOX_ENABLED") != "true":
        pytest.skip("needs an OTLP-exporting platform with the sandbox tool (SANDBOX_ENABLED)")
    otlp_sink.sink()
    token = tenant_token("tenant-a")
    tool = "sandbox__execute_python"
    trace: list[dict] = []
    text = ""
    for _ in range(3):  # retry only when the model skips the tool; a refusal fails at once
        thread, out = run(graph, token, BENIGN_PROMPT)
        assert run_error(out) is None, run_error(out)
        text = final_text(out)
        assert REFUSAL not in text, f"{graph}: rail refused benign code"
        trace = otlp_sink.trace_for_session(graph, thread, want=1, want_tool=tool)
        if any(otlp_sink.attr(s, "gen_ai.tool.name") == tool for s in trace):
            break
    spans = [s for s in trace if otlp_sink.attr(s, "gen_ai.tool.name") == tool]
    assert spans, f"{graph}: model never called {tool}"
    # the sidecar's tool span carries the sandbox result; the gateway's tools/call span does not
    outcomes = [otlp_sink.attr(s, "sandbox.outcome") for s in spans if otlp_sink.attr(s, "sandbox.outcome")]
    assert outcomes and outcomes[-1] == "allowed", [s["attrs"][:200] for s in spans]
    assert "45" in text, text[:300]
    assert not [s["name"] for s in trace if otlp_sink.attr(s, "error.type")], "failed span in the run"
