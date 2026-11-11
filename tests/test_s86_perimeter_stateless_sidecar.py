"""S-86: the stateless (zero-DB) perimeter sidecar still enforces P18 (live).

Needs KUBECONTEXT and PERIMETER_GRAPH (the graph id of an agent deployed with
`zelkor deploy --egress-only`). The zero-DB mode must not weaken the runtime promise:
no DB credentials, no migrate, egress held by the gateway + pod NetworkPolicy.
"""
from __future__ import annotations

import json
import os

import pytest

from tests.helpers.kube import kubectl_run
from tests.helpers.runtime_agents import deployment, exec_python, require_kube

# Reports presence only — never prints a secret value.
PROBE = r"""
import json, os, socket
def tcp(host, port):
    try:
        socket.create_connection((host, port), timeout=4).close(); return "open"
    except Exception as e:
        return type(e).__name__
print(json.dumps({
    "has_db": "DATABASE_URL" in os.environ,
    "has_redis": "REDIS_URL" in os.environ,
    "openai_placeholder": os.environ.get("OPENAI_API_KEY", "") == "via-sidecar",
    "pypi": tcp("pypi.org", 443),
}))
"""


def _graph() -> str:
    g = os.environ.get("PERIMETER_GRAPH", "").strip()
    if not g:
        pytest.skip("PERIMETER_GRAPH not set (deploy an agent with `zelkor deploy --egress-only`)")
    return g


def test_stateless_sidecar_has_no_db_and_no_migrate():
    require_kube()
    graph = _graph()
    res = kubectl_run(["get", deployment(graph), "-o", "json"])
    assert res.returncode == 0, res.stderr
    spec = json.loads(res.stdout)["spec"]["template"]["spec"]
    assert not spec.get("initContainers"), "stateless perimeter sidecar must have no migrate init-container"
    (sidecar,) = [c for c in spec["containers"] if c["name"] == "sidecar"]
    env = {e["name"]: e.get("value") for e in sidecar.get("env") or []}
    assert "DATABASE_URL" not in env
    assert env.get("ZELKOR_SIDECAR_STORE") == "memory"


def test_runtime_holds_no_db_credentials():
    require_kube()
    graph = _graph()
    out = json.loads(exec_python(graph, "agent", PROBE))
    assert out["has_db"] is False and out["has_redis"] is False
    # the agent never holds a provider key; the sidecar injects the real one on egress
    assert out["openai_placeholder"] is True


def test_runtime_cannot_leave_the_gateway():
    # Egress enforcement needs the pod NetworkPolicy enforced by the CNI (Path B). Skip otherwise.
    if not os.environ.get("PERIMETER_NP_ENFORCED", "").strip():
        pytest.skip("set PERIMETER_NP_ENFORCED=1 on a cluster whose CNI enforces NetworkPolicies")
    require_kube()
    graph = _graph()
    out = json.loads(exec_python(graph, "agent", PROBE))
    assert out["pypi"] != "open", f"runtime reached the public internet directly: {out['pypi']}"
