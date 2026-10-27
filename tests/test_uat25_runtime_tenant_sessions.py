"""UAT-25 / S-74: one runtime pod serves tenant A, B, A; every tool call works in its own trace (live).

The MCP gateway binds a session to the identity that opened it. Runtimes such as OpenCode keep
one MCP session across runs; the sidecar must reopen it per run instead of reusing A's session
with B's bearer (that returned 401 on every tools/call).
"""
from __future__ import annotations

import os

import pytest

from tests.helpers.runtime_agents import (
    error_spans, runtime_graphs, sandbox_run, tenant_id, tenant_token, tool_spans,
)


def _session_graph() -> str:
    graph = os.environ.get("ZELKOR_SESSION_GRAPH", "").strip()
    if graph:
        return graph
    graphs = runtime_graphs()
    return next((g for g in graphs if "opencode" in g), graphs[0])


def test_uat25_alternating_tenants_each_get_working_tool_calls():
    graph = _session_graph()
    a, b = tenant_token("tenant-a"), tenant_token("tenant-b")
    assert tenant_id(a) != tenant_id(b), "tenant-a and tenant-b tokens carry the same tenant"
    for token in (a, b, a):
        full, sandbox = sandbox_run(graph, token)
        assert tool_spans(full), f"{tenant_id(token)}: model never called the tool in 3 attempts"
        assert {o.get("userId") for o in full if o.get("userId")} == {tenant_id(token)}
        assert error_spans(full) == [], f"{tenant_id(token)}: {error_spans(full)}"
        assert sandbox and sandbox.get("outcome") == "denied", sandbox
