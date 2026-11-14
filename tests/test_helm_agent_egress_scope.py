"""Effective egress of a wrapped agent pod: its own policies plus every platform policy that selects it.

NetworkPolicy allows add up, so a platform policy that matches an agent's labels widens that agent.
`--egress-only` (stateless sidecar) promises gateway + DNS (+ the trace sink); a stateful agent also
needs its database; only the Aegra runtime needs Valkey (its broker). Rendered, no cluster.
"""
from __future__ import annotations

import subprocess

import pytest
import yaml

from tests.test_agent_health_probes import _helm_agent
from tests.test_helm_values_schema import CHART, PROFILES

NS = "zelkor"
DATASTORES = {"postgresql", "valkey", "cnpg"}


def _platform_policies() -> list[dict]:
    cmd = ["helm", "template", "zelkor-platform", str(CHART), "--namespace", NS,
           "-f", str(PROFILES / "values-local.yaml")]
    r = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert r.returncode == 0, r.stderr
    docs = [d for d in yaml.safe_load_all(r.stdout) if d and d.get("kind") == "NetworkPolicy"]
    assert any(d["metadata"]["name"].endswith("-aegra-egress") for d in docs), "fixture: full profile with Aegra"
    return docs


def _agent(*extra: str) -> tuple[dict, list[dict]]:
    r = _helm_agent("--set", "security.networkPolicies.enabled=true",
                    "--set", "image.repository=ghcr.io/acme/agent", *extra)
    assert r.returncode == 0, r.stderr
    docs = [d for d in yaml.safe_load_all(r.stdout) if d]
    (dep,) = [d for d in docs if d.get("kind") == "Deployment"]
    return dep["spec"]["template"]["metadata"]["labels"], [d for d in docs if d.get("kind") == "NetworkPolicy"]


def _selects(selector: dict, labels: dict) -> bool:
    for k, v in (selector.get("matchLabels") or {}).items():
        if labels.get(k) != v:
            return False
    for e in selector.get("matchExpressions") or []:
        key, op, values = e["key"], e["operator"], e.get("values") or []
        if (op == "In" and labels.get(key) not in values) or (op == "NotIn" and labels.get(key) in values) \
                or (op == "Exists" and key not in labels) or (op == "DoesNotExist" and key in labels):
            return False
    return True


def _destinations(labels: dict, policies: list[dict]) -> set[str]:
    """Datastore-ish destinations any egress policy selecting this pod allows."""
    out: set[str] = set()
    for np in policies:
        spec = np["spec"]
        if "Egress" not in (spec.get("policyTypes") or []) or not _selects(spec.get("podSelector") or {}, labels):
            continue
        for rule in spec.get("egress") or []:
            for peer in rule.get("to") or []:
                pod = peer.get("podSelector") or {}
                comp = (pod.get("matchLabels") or {}).get("app.kubernetes.io/component")
                if comp:
                    out.add(comp)
                if any(e.get("key") == "cnpg.io/cluster" for e in pod.get("matchExpressions") or []):
                    out.add("cnpg")
    return out


@pytest.fixture(scope="module")
def platform() -> list[dict]:
    return _platform_policies()


def test_egress_only_agent_reaches_no_datastore(platform):
    labels, own = _agent("--set", "runtime=a2a", "--set", "sidecar.stateless=true")
    reach = _destinations(labels, platform + own)
    assert not reach & DATASTORES, f"--egress-only agent may reach {sorted(reach & DATASTORES)}"


@pytest.mark.parametrize("runtime", ["a2a", "opencode"])
def test_stateful_sidecar_agent_reaches_postgres_not_valkey(platform, runtime):
    labels, own = _agent("--set", f"runtime={runtime}")
    reach = _destinations(labels, platform + own)
    assert "postgresql" in reach, "the stateful sidecar keeps its store in Postgres"
    assert "valkey" not in reach, "only the Aegra runtime uses the Valkey broker"


def test_aegra_runtime_agent_reaches_postgres_and_valkey(platform):
    labels, own = _agent("--set", "runtime=aegra")
    reach = _destinations(labels, platform + own)
    assert {"postgresql", "valkey"} <= reach
