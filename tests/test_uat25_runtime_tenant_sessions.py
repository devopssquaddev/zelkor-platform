"""UAT-25 / S-74: one runtime pod serves tenant A, B, A; every tool call works in its own trace (live).

The MCP gateway binds a session to the identity that opened it. Runtimes such as OpenCode keep
one MCP session across runs; the sidecar must reopen it per run instead of reusing A's session
with B's bearer (that returned 401 on every tools/call).

The trace backend follows the platform: Langfuse (sandbox tool, full profile) or, when the
platform contract has OTLP_RELAY_SERVICE, the OTLP collector sink with any gateway tool
(ZELKOR_SESSION_TOOL, default MCP_AUDIT_TOOL; arguments from MCP_POLICY_TOOL_ARGS). A perimeter
without an OTLP endpoint has no trace backend: the backend's tools_call audit is the evidence.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
import uuid
from datetime import datetime, timezone

import pytest

from tests.helpers import otlp_sink
from tests.helpers.kube import kubectl_cmd, platform_contract
from tests.helpers.runtime_agents import (
    error_spans, require_kube, run, run_error, runtime_graphs, sandbox_run, tenant_id, tenant_token,
    tool_spans,
)


def _session_graph() -> str:
    graph = os.environ.get("ZELKOR_SESSION_GRAPH", "").strip()
    if graph:
        return graph
    graphs = runtime_graphs()
    return next((g for g in graphs if "opencode" in g), graphs[0])


def _contract() -> dict[str, str]:
    return platform_contract(os.environ.get("ZELKOR_PLATFORM_NAMESPACE", "zelkor"))


def _tool_audit(tool: str, tenant: str, since: str = "3m") -> list[dict]:
    """The tool backend's metadata-only tools_call records for one tenant (CE-9c S-73)."""
    release = os.environ.get("ZELKOR_RELEASE", "zelkor-platform")
    backend, short = tool.split("__", 1)
    proc = subprocess.run(kubectl_cmd("logs", f"deploy/{release}-mcp-{backend}", f"--since={since}"),
                          capture_output=True, text=True, timeout=60, check=False)
    assert proc.returncode == 0, proc.stderr[-300:]
    records = []
    for line in proc.stdout.splitlines():
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if rec.get("event") == "tools_call" and rec.get("tool") == short and rec.get("tenant_id") == tenant:
            records.append(rec)
    return records


def _otlp_tool_run(graph: str, token: str, tool: str, attempts: int = 3,
                   traced: bool = True) -> tuple[list[dict], list[dict]]:
    """One run whose `tool` call succeeds at the backend. Retry when the model skips the tool or
    only sends malformed arguments (gpt-oss sometimes stringifies `messages`): model behavior."""
    raw = os.environ.get("MCP_POLICY_TOOL_ARGS", "").strip()
    if not raw:
        pytest.skip("MCP_POLICY_TOOL_ARGS not set (arguments for the session tool)")
    trace: list[dict] = []
    for attempt in range(attempts):
        args = raw.replace("{canary}", uuid.uuid4().hex[:8])
        started = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        thread, out = run(graph, token, f"Call the {tool} tool exactly once with these arguments, "
                                        f"then report what it returned:\n{args}")
        assert run_error(out) is None, run_error(out)
        trace = otlp_sink.trace_for_session(graph, thread, want=1, want_tool=tool) if traced else []
        if not traced or any(otlp_sink.attr(s, "gen_ai.tool.name") == tool for s in trace):
            time.sleep(2)
            # ISO timestamps compare as strings; the log window slides, so filter by time, not count
            audit = [r for r in _tool_audit(tool, tenant_id(token)) if str(r.get("timestamp", "")) >= started]
            if any(r.get("status") == "ok" for r in audit) or attempt == attempts - 1:
                return trace, audit
    return trace, []


def _langfuse_case(graph: str, tokens: list[str]) -> None:
    for token in tokens:
        full, sandbox = sandbox_run(graph, token)
        assert tool_spans(full), f"{tenant_id(token)}: model never called the tool in 3 attempts"
        assert {o.get("userId") for o in full if o.get("userId")} == {tenant_id(token)}
        assert error_spans(full) == [], f"{tenant_id(token)}: {error_spans(full)}"
        assert sandbox and sandbox.get("outcome") == "denied", sandbox


def _session_tool() -> str:
    tool = (os.environ.get("ZELKOR_SESSION_TOOL") or os.environ.get("MCP_AUDIT_TOOL") or "").strip()
    if "__" not in tool:
        pytest.skip("ZELKOR_SESSION_TOOL / MCP_AUDIT_TOOL (<backend>__<tool>) not set")
    return tool


def _audit_case(graph: str, tokens: list[str]) -> None:
    """No trace backend (perimeter without OTLP): each tenant's call reaches the backend as itself."""
    require_kube()
    tool = _session_tool()
    for token in tokens:
        _, audit = _otlp_tool_run(graph, token, tool, traced=False)
        # a reused foreign session never reaches the backend (401 at the gateway)
        assert "ok" in {r.get("status") for r in audit}, f"{tenant_id(token)}: no ok tools_call: {audit}"


def _otlp_case(graph: str, tokens: list[str]) -> None:
    require_kube()
    otlp_sink.sink()
    tool = _session_tool()
    for token in tokens:
        tenant = tenant_id(token)
        trace, audit = _otlp_tool_run(graph, token, tool)
        assert any(otlp_sink.attr(s, "gen_ai.tool.name") == tool for s in trace), \
            f"{tenant}: model never called {tool} in 3 attempts"
        assert {otlp_sink.attr(s, "user.id") for s in trace if otlp_sink.attr(s, "user.id")} == {tenant}
        # the call reached the backend as this tenant (a reused foreign session is a 401 at the gateway)
        assert audit, f"{tenant}: no tools_call record for {tool} at the backend"
        # a model that drops an argument gets a backend validation error and retries (model
        # behavior); a reused foreign session never reaches the backend (401 at the gateway)
        assert "ok" in {r.get("status") for r in audit}, audit


def test_uat25_alternating_tenants_each_get_working_tool_calls():
    graph = _session_graph()
    a, b = tenant_token("tenant-a"), tenant_token("tenant-b")
    assert tenant_id(a) != tenant_id(b), "tenant-a and tenant-b tokens carry the same tenant"
    contract = _contract()
    if contract.get("OTLP_RELAY_SERVICE"):
        case = _otlp_case
    elif contract.get("PROFILE") == "perimeter":
        case = _audit_case
    else:
        case = _langfuse_case
    case(graph, [a, b, a])
