"""CE-1: values.schema.json, extraManifests, provenance labels, tier gates."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "charts" / "zelkor-platform"
PROFILES = ROOT / "profiles"
SCHEMA_PATH = CHART / "values.schema.json"
FINSERVE_OVERLAYS = [
    ROOT / "examples" / "finserve" / "chart" / "values-platform-overlay.yaml",
    ROOT / "examples" / "finserve" / "chart" / "values-platform-overlay-local.yaml",
    ROOT / "examples" / "finserve" / "chart" / "values-platform-overlay-tenants.yaml",
]

SECRET_SETS = [
    "postgresql.auth.password=test-pg",
    "clickhouse.auth.password=test-ch",
    "seaweedfs.auth.accessKey=test-ak",
    "seaweedfs.auth.secretKey=test-sk",
    "platform.telemetry.langfuse.nextauthSecret=test-na",
    "platform.telemetry.langfuse.salt=test-salt-1234567890",
    "platform.telemetry.langfuse.encryptionKey=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    "platform.telemetry.langfuse.nextauthUrl=https://langfuse.example.com",
    "platform.telemetry.langfuse.admin.email=admin@example.com",
    "gateway.hosts.langfuse=langfuse.example.com",
    "gateway.hosts.agents=agents.example.com",
    "gateway.hosts.aiGateway=ai.example.com",
    "gateway.hosts.mcp=mcp.example.com",
    "gateway.hosts.nemo=nemo.example.com",
]

INTENT_KINDS = frozenset(
    {
        "Deployment",
        "StatefulSet",
        "Job",
        "Service",
        "HTTPRoute",
        "AIServiceBackend",
        "AIGatewayRoute",
        "Backend",
        "BackendTLSPolicy",
        "BackendTrafficPolicy",
        "ClientTrafficPolicy",
        "SecurityPolicy",
        "MCPRoute",
    }
)


def _helm(*extra: str, values_files: list[Path] | None = None) -> subprocess.CompletedProcess[str]:
    cmd = ["helm", "template", "zelkor-platform", str(CHART), "--namespace", "zelkor"]
    for item in SECRET_SETS:
        cmd.extend(["--set", item])
    for vf in values_files or []:
        cmd.extend(["-f", str(vf)])
    cmd.extend(extra)
    return subprocess.run(cmd, check=False, capture_output=True, text=True)


def _docs(rendered: str) -> list[dict]:
    return list(yaml.safe_load_all(rendered))


def test_schema_file_exists_and_valid_json():
    assert SCHEMA_PATH.is_file()
    json.loads(SCHEMA_PATH.read_text())


def test_default_and_profiles_render():
    assert _helm().returncode == 0, _helm().stderr
    for profile in PROFILES.glob("values*.yaml"):
        r = _helm(values_files=[profile])
        assert r.returncode == 0, f"{profile.name}: {r.stderr}"


def test_finserve_platform_overlays_on_local_profile_render():
    local = PROFILES / "values-local.yaml"
    for overlay in FINSERVE_OVERLAYS:
        if not overlay.is_file():
            continue
        r = _helm(values_files=[local, overlay])
        assert r.returncode == 0, f"{overlay.name}: {r.stderr}"


def test_unknown_top_level_key_fails_schema():
    r = _helm("--set", "aiGatway.enabled=true")
    assert r.returncode != 0
    assert "aiGatway" in r.stderr


def test_unknown_nested_provider_key_fails_schema():
    r = _helm("--set", "workspace.models.providers.opneai.apiKey=x")
    assert r.returncode != 0
    assert "opneai" in r.stderr


def test_invalid_logging_level_fails_schema():
    r = _helm("--set", "platform.telemetry.level=verbose")
    assert r.returncode != 0


def test_invalid_databases_mode_fails_schema():
    r = _helm("--set", "databases.mode=invalid-mode")
    assert r.returncode != 0


def test_tier_gate_auth_sso():
    r = _helm("--set", "platform.tenants.sso.enabled=true")
    assert r.returncode != 0
    assert "Pro" in r.stderr


def test_tier_gate_mtls():
    r = _helm("--set", "platform.mTLS.enabled=true")
    assert r.returncode != 0
    assert "Enterprise" in r.stderr


def test_tier_gate_llama_guard():
    r = _helm("--set", "workspace.policies.llamaGuard.enabled=true")
    assert r.returncode != 0
    assert "Enterprise" in r.stderr


def test_tier_gate_global_tier():
    r = _helm("--set", "global.tier=pro")
    assert r.returncode != 0
    assert "Pro" in r.stderr or "umbrella" in r.stderr


def test_extra_manifests_renders_alongside_chart():
    r = _helm(
        "--set",
        'extraManifests[0].apiVersion=v1',
        "--set",
        'extraManifests[0].kind=ConfigMap',
        "--set",
        'extraManifests[0].metadata.name=customer-hook',
    )
    assert r.returncode == 0, r.stderr
    docs = _docs(r.stdout)
    cm = [d for d in docs if d and d.get("kind") == "ConfigMap" and d.get("metadata", {}).get("name") == "customer-hook"]
    assert cm
    deploys = [d for d in docs if d and d.get("kind") == "Deployment"]
    assert deploys


def test_extra_manifests_default_empty():
    r = _helm()
    assert r.returncode == 0
    assert "customer-hook" not in r.stdout


def test_provenance_labels_on_workloads():
    r = _helm(values_files=[PROFILES / "values-local.yaml"])
    assert r.returncode == 0, r.stderr
    missing = []
    for doc in _docs(r.stdout):
        if not doc or doc.get("kind") not in INTENT_KINDS:
            continue
        labels = doc.get("metadata", {}).get("labels") or {}
        if "zelkor.io/intent" not in labels:
            missing.append(f"{doc['kind']}/{doc.get('metadata', {}).get('name')}")
    assert not missing, "missing zelkor.io/intent: " + ", ".join(missing[:10])


def test_openai_provider_intent_when_key_set():
    r = _helm("--set", "workspace.models.providers.openai.apiKey=sk-test")
    assert r.returncode == 0, r.stderr
    found = False
    for doc in _docs(r.stdout):
        if doc and doc.get("kind") == "AIServiceBackend":
            intent = (doc.get("metadata", {}).get("labels") or {}).get("zelkor.io/intent", "")
            if intent == "aiGateway.providers.openai":
                found = True
                break
    assert found


def test_template_values_paths_have_schema_properties():
    """Top-level values keys referenced in templates appear in values.schema.json."""
    schema = json.loads(SCHEMA_PATH.read_text())
    props = set(schema.get("properties", {}).keys())
    paths = set()
    for p in (CHART / "templates").rglob("*"):
        if p.suffix not in (".yaml", ".tpl"):
            continue
        text = p.read_text(errors="ignore")
        for m in re.finditer(r"\.Values\.([a-zA-Z0-9_]+)", text):
            paths.add(m.group(1))
    allowed = props | {
        "Chart",
        "Release",
        "Capabilities",
        "Template",
        "__compiled",
        "__workloadIntent",
        "__mcpExtraBackendJson",
        "__mcpExtraBackendEnv",
        "__mcpExtraBackendVolumes",
        "__mcpExtraBackendVolumeMounts",
        "__mcpExtraBackendIpBlocks",
    }
    stray = sorted(paths - allowed)
    assert not stray, f"template references without schema property: {stray}"
