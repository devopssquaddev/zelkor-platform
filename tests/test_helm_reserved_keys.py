"""S-23 (PRO) L2: every reserved Pro/Enterprise key in templates/validate.yaml fails the CE render
and names its tier; the matching umbrella entitlement lifts exactly that gate."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.test_helm_values_schema import CHART, _helm

# (values to set, tier named in the error, entitlement that lifts it or None)
GATES = {
    "sso": (["platform.tenants.sso.enabled=true"], "Pro", "sso"),
    "mtls": (["platform.mTLS.enabled=true"], "Enterprise", "mTLS"),
    "llama_guard": (["workspace.policies.llamaGuard.enabled=true"], "Enterprise", "llamaGuard"),
    "presidio": (["workspace.policies.presidio.enabled=true"], "Enterprise", "presidio"),
    "worm_audit": (["platform.telemetry.audit.worm.enabled=true"], "Enterprise", "wormAudit"),
    "dual_trace_sink": (["platform.telemetry.otlp.endpoint=http://otel.example.svc:4318"], "Pro", None),
    "global_tier": (["global.tier=pro"], "umbrella", "tier"),
    "hitl_approval": (["workload.intent.approval.enabled=true"], "Pro", None),
}


def _sets(values: list[str]) -> list[str]:
    return [a for v in values for a in ("--set", v)]


def test_every_validate_gate_is_listed():
    """A new reserved key in validate.yaml must get a row here (and an S-23 note)."""
    src = (CHART / "templates" / "validate.yaml").read_text()
    gated = set(re.findall(r'hasEntitlement" \(dict "Values" \.Values "name" "(\w+)"\)', src))
    listed = {ent for _, _, ent in GATES.values() if ent}
    assert gated == listed, f"validate.yaml gates {sorted(gated - listed)} have no row; stale rows {sorted(listed - gated)}"


@pytest.mark.parametrize("gate", sorted(GATES))
def test_s23_reserved_key_fails_ce_render(gate):
    values, tier, _ = GATES[gate]
    r = _helm(*_sets(values))
    assert r.returncode != 0, f"{gate}: CE render accepted a reserved key"
    assert tier in r.stderr, r.stderr[-400:]


@pytest.mark.parametrize("gate", sorted(g for g, (_, _, ent) in GATES.items() if ent and ent != "tier"))
def test_entitlement_lifts_only_its_own_gate(gate):
    values, _, ent = GATES[gate]
    r = _helm(*_sets(values), "--set", f"global.zelkor.entitlements[0]={ent}")
    assert "requires Zelkor" not in r.stderr, f"{gate}: entitlement {ent} did not lift its gate: {r.stderr[-300:]}"
    other = next(g for g in GATES if g != gate and GATES[g][2] and GATES[g][2] != "tier")
    r2 = _helm(*_sets(values), "--set", f"global.zelkor.entitlements[0]={GATES[other][2]}")
    assert r2.returncode != 0, f"{gate}: entitlement {GATES[other][2]} lifted the wrong gate"
