"""UAT-24: non-Aegra runtime agents run governed (live; skips without ZELKOR_RUNTIME_GRAPHS).

Pair with ``AEGRA_WORKER_GRAPH_ID=<graph> pytest tests/test_drop_in_langgraph_sdk.py`` per graph.
"""
from __future__ import annotations

import json

import pytest

from tests.helpers.kube import kubectl_run
from tests.helpers.runtime_agents import (
    error_spans, require_kube, runtime_graphs, sandbox_run, tenant_id, tenant_token,
)


def _graphs():
    try:
        return runtime_graphs()
    except pytest.skip.Exception:
        return []


@pytest.mark.parametrize("graph", _graphs() or [pytest.param("-", marks=pytest.mark.skip("ZELKOR_RUNTIME_GRAPHS not set"))])
def test_uat24_sandbox_run_is_one_governed_trace(graph):
    token = tenant_token("tenant-a")
    full, sandbox = sandbox_run(graph, token)
    roots = {str(o.get("name")) for o in full if not o.get("parentObservationId")}
    users = {o.get("userId") for o in full if o.get("userId")}
    assert roots == {graph}, roots
    assert users == {tenant_id(token)}, users
    assert len({o.get("traceId") for o in full}) == 1
    assert any(str(o.get("type")).upper() == "GENERATION" for o in full), "no LLM generation in the run trace"
    assert sandbox and sandbox.get("violation") == "permission_denied_mknod", sandbox
    assert error_spans(full) == [], error_spans(full)


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
