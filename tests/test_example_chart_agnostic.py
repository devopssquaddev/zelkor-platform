"""Example charts ship no kind/test-cluster Service DNS or lab secrets."""
from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
AGENT_CHART = ROOT / "charts" / "zelkor-agent"
FINSERVE_CHART = ROOT / "examples" / "finserve" / "chart"
FINSERVE_VALUES = FINSERVE_CHART / "values.yaml"
FINSERVE_LOCAL = FINSERVE_CHART / "values-local.yaml"
FINSERVE_OVERLAY = FINSERVE_CHART / "values-platform-overlay.yaml"
FINSERVE_OVERLAY_LOCAL = FINSERVE_CHART / "values-platform-overlay-local.yaml"

KIND_DNS = (
    "zelkor-platform-ai-gateway",
    "zelkor-platform-mcp-gateway",
    "zelkor-platform-postgresql",
    "zelkor-platform-qdrant",
    "zelkor-platform-langfuse",
    "zelkor-platform-valkey",
    "zelkor-platform-gateway",
)


def _helm(chart: Path, release: str, *extra: str) -> subprocess.CompletedProcess[str]:
    cmd = ["helm", "template", release, str(chart), "--namespace", "zelkor", *extra]
    return subprocess.run(cmd, check=False, capture_output=True, text=True)


def _ensure_finserve_deps() -> None:
    proc = subprocess.run(
        ["helm", "dependency", "update", str(FINSERVE_CHART)],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(FINSERVE_CHART),
    )
    assert proc.returncode == 0, proc.stderr


def test_finserve_values_have_no_kind_literals():
    raw = FINSERVE_VALUES.read_text()
    for token in KIND_DNS:
        assert token not in raw, token
    assert "gpt-oss:20b" not in raw
    assert "zelkor-dev-password" not in raw
    assert "dev-key" not in raw
    assert "pk-lf-zelkor-dev" not in raw
    values = yaml.safe_load(raw)
    assert values["platform"]["releaseName"] == ""
    assert values["platform"]["postgresHost"] == ""
    assert values["gateway"]["namespace"] == ""
    for key in ("desk", "quant", "coder"):
        assert values[key]["platform"]["openaiBaseUrl"] == ""
        assert values[key]["platform"]["mcpUrl"] == ""
        assert values[key]["sharedRoute"]["gatewayNamespace"] == ""
        assert values[key]["platform"]["defaultLlmModel"] == ""


def test_zelkor_agent_values_have_no_kind_urls():
    raw = (AGENT_CHART / "values.yaml").read_text()
    assert "zelkor-platform-ai-gateway" not in raw
    assert "zelkor-platform-mcp-gateway" not in raw
    values = yaml.safe_load(raw)
    assert values["platform"]["openaiBaseUrl"] == ""
    assert values["platform"]["mcpUrl"] == ""
    assert values["platform"]["releaseName"] == ""


def test_finserve_overlay_is_domain_only():
    raw = FINSERVE_OVERLAY.read_text()
    assert "zelkor-dev-password" not in raw
    assert "databaseUrl:" not in raw
    for token in KIND_DNS:
        assert token not in raw, token
    assert "finserve_policies" in raw


def test_finserve_overlay_local_has_kind_dsn():
    raw = FINSERVE_OVERLAY_LOCAL.read_text()
    assert "zelkor-dev-password" in raw
    assert "zelkor-platform-postgresql" in raw


def test_finserve_helm_empty_values_requires_connection():
    _ensure_finserve_deps()
    proc = _helm(FINSERVE_CHART, "finserve")
    assert proc.returncode != 0
    assert "platform.releaseName" in proc.stderr or "must be set" in proc.stderr


def test_finserve_helm_values_local_emits_kind_dns():
    _ensure_finserve_deps()
    proc = _helm(FINSERVE_CHART, "finserve", "-f", str(FINSERVE_LOCAL))
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    assert "zelkor-platform-postgresql" in out
    assert "zelkor-platform-qdrant" in out
    assert "zelkor-platform-langfuse" in out
    assert "zelkor-platform-ai-gateway" in out
    assert "agents.localhost" in out
    assert "pk-lf-zelkor-dev" not in (FINSERVE_CHART / "templates" / "job-langfuse-seed.yaml").read_text()


def test_zelkor_agent_release_name_constructs_urls():
    proc = _helm(
        AGENT_CHART,
        "demo-agent",
        "--set",
        "graphId=demo-graph",
        "--set",
        "platform.databaseUrl=postgres://zelkor:x@pg:5432/aegra",
        "--set",
        "platform.valkeyUrl=redis://vk:6379/0",
        "--set",
        "platform.releaseName=my-platform",
        "--set",
        "sharedRoute.host=agents.example.com",
    )
    assert proc.returncode == 0, proc.stderr
    assert "http://my-platform-ai-gateway:80/v1" in proc.stdout
    assert "http://my-platform-mcp-gateway:8080" in proc.stdout
    assert "my-platform-gateway" in proc.stdout


def test_zelkor_agent_explicit_url_wins_over_release_name():
    proc = _helm(
        AGENT_CHART,
        "demo-agent",
        "--set",
        "graphId=demo-graph",
        "--set",
        "platform.databaseUrl=postgres://zelkor:x@pg:5432/aegra",
        "--set",
        "platform.releaseName=my-platform",
        "--set",
        "platform.openaiBaseUrl=http://custom-gw:80/v1",
        "--set",
        "platform.mcpUrl=http://custom-mcp:8080",
    )
    assert proc.returncode == 0, proc.stderr
    assert "http://custom-gw:80/v1" in proc.stdout
    assert "http://custom-mcp:8080" in proc.stdout
    assert "http://my-platform-ai-gateway:80/v1" not in proc.stdout


def test_agent_python_has_no_kind_model_default():
    for name in ("advisor_agent.py", "research_agent.py", "quant_agent.py"):
        text = (FINSERVE_CHART / "files" / name).read_text()
        assert 'os.getenv("DEFAULT_LLM_MODEL", "")' in text
        assert "gpt-oss:20b" not in text
