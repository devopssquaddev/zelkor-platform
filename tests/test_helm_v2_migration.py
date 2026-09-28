"""V2 helm render gates: compile hook, V1 fail-fast, contract ConfigMap."""
from __future__ import annotations

from tests.test_helm_values_schema import CHART, _docs, _helm


def test_every_template_invokes_v2_compiler():
    missing = []
    for p in (CHART / "templates").rglob("*.yaml"):
        if p.name == "_helpers.tpl":
            continue
        text = p.read_text()
        if "zelkor-platform.compile" not in text:
            missing.append(str(p.relative_to(CHART)))
    assert not missing, "missing compile include: " + ", ".join(missing[:8])


def test_v1_ai_gateway_fails_with_migration_message():
    r = _helm("--set", "aiGateway.enabled=true")
    assert r.returncode != 0
    assert "workspace.models" in r.stderr


def test_unknown_workspace_key_fails_schema():
    r = _helm("--set", "workspace.notARealKnob=true")
    assert r.returncode != 0


def test_platform_contract_configmap_present():
    r = _helm()
    assert r.returncode == 0, r.stderr
    cms = [
        d
        for d in _docs(r.stdout)
        if d and d.get("kind") == "ConfigMap" and d.get("metadata", {}).get("name") == "zelkor-platform-contract"
    ]
    assert len(cms) == 1
    data = cms[0].get("data") or {}
    assert data.get("CONTRACT_VERSION") == "v2.0"
    assert "AI_GATEWAY_SERVICE" in data
    assert "zelkor-platform-ai-gateway" in data["AI_GATEWAY_SERVICE"]
