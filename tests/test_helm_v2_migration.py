"""V2 helm render gates: golden snapshots, compile hook, V1 fail-fast, contract ConfigMap."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

import yaml

from tests.test_helm_values_schema import CHART, PROFILES, SECRET_SETS, _docs, _helm

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "tests" / "fixtures" / "helm_golden_v126"


def _norm_render(text: str) -> str:
    text = re.sub(r'app\.kubernetes\.io/version: "[^"]+"', 'app.kubernetes.io/version: "X"', text)
    text = re.sub(r"helm\.sh/chart: zelkor-platform-[^\n]+", "helm.sh/chart: zelkor-platform-X", text)
    docs = [d for d in yaml.safe_load_all(text) if d]
    scrubbed = []
    for doc in docs:
        d = dict(doc)
        if d.get("kind") == "Secret":
            data = d.get("data") or {}
            d["data"] = {k: "REDACTED" for k in data}
            if "stringData" in d:
                d["stringData"] = {k: "REDACTED" for k in (d.get("stringData") or {})}
        scrubbed.append(d)
    scrubbed.sort(key=lambda d: (d.get("kind", ""), d.get("metadata", {}).get("name", "")))
    return yaml.dump_all(scrubbed, sort_keys=True)


def test_profiles_match_v126_golden_manifests():
    for profile in sorted(PROFILES.glob("values*.yaml")):
        r = _helm(values_files=[profile])
        assert r.returncode == 0, f"{profile.name}: {r.stderr}"
        golden_path = GOLDEN / f"{profile.stem}.yaml"
        assert golden_path.is_file(), f"missing golden {golden_path}"
        assert _norm_render(r.stdout) == _norm_render(golden_path.read_text()), profile.name


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
