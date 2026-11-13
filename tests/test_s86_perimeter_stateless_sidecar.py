"""S-86: a stateless (zero-DB) sidecar wrap holds no database at all (live).

Applies to every runtime agent wrapped statelessly: on a profile=perimeter platform (where
`zelkor deploy` always does this) or with `--egress-only` on full. Needs KUBECONTEXT and
ZELKOR_RUNTIME_GRAPHS; skips when none of those agents is stateless. What the runtime container
can reach on its own (no credentials, no public egress, no model without the sidecar) is S-75,
which runs against the same agents.
"""
from __future__ import annotations

import json

import pytest

from tests.helpers.kube import kubectl_run
from tests.helpers.runtime_agents import deployment, require_kube, runtime_graphs


def _sidecar_env(spec: dict) -> dict[str, str]:
    (sidecar,) = [c for c in spec["containers"] if c["name"] == "sidecar"]
    return {e["name"]: e.get("value") for e in sidecar.get("env") or []}


def test_stateless_sidecar_has_no_db_and_no_migrate():
    require_kube()
    checked = []
    for graph in runtime_graphs():
        res = kubectl_run(["get", deployment(graph), "-o", "json"])
        assert res.returncode == 0, res.stderr
        spec = json.loads(res.stdout)["spec"]["template"]["spec"]
        env = _sidecar_env(spec)
        if env.get("ZELKOR_SIDECAR_STORE") != "memory":
            continue
        assert not spec.get("initContainers"), f"{graph}: stateless sidecar must have no migrate init-container"
        assert "DATABASE_URL" not in env, graph
        checked.append(graph)
    if not checked:
        pytest.skip("no stateless-wrapped runtime agent among ZELKOR_RUNTIME_GRAPHS")
