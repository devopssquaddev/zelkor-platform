"""UAT-21: official example is a slim-fit zelkor-agent copy target."""
from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
FINSERVE = ROOT / "examples" / "finserve"
VALUES = FINSERVE / "chart" / "values.yaml"
README = FINSERVE / "README.md"
OVERLAY = FINSERVE / "chart" / "values-platform-overlay.yaml"
WORKERS = ("desk", "quant", "coder")
INHERIT_PLATFORM = (
    "openaiBaseUrl",
    "mcpUrl",
    "consumerKey",
    "mcpInject",
    "defaultLlmModel",
)


def _values() -> dict:
    return yaml.safe_load(VALUES.read_text())


def test_uat21_overlay_uses_workspace_tools():
    raw = OVERLAY.read_text()
    assert "workspace:" in raw
    assert "tools:" in raw
    assert "mcp.postgresMCP" not in raw
    assert "mcp.extraBackends" not in raw


def test_uat21_extra_mcp_off_by_default():
    values = _values()
    assert values["extraMcp"]["enabled"] is False
    assert "workspace.tools.extraBackends" not in VALUES.read_text()


def test_uat21_readme_teaches_workspace_tools():
    raw = README.read_text()
    assert "mcp.postgresMCP" not in raw
    assert "mcp.extraBackends" not in raw
    assert "workspace.tools" in raw


def test_uat21_workers_omit_inherit_keys():
    values = _values()
    restated: list[str] = []
    for name in WORKERS:
        worker = values[name]
        plat = worker.get("platform") or {}
        for key in INHERIT_PLATFORM:
            if key in plat:
                restated.append(f"{name}.platform.{key}")
        if "replicaCount" in worker:
            restated.append(f"{name}.replicaCount")
        if (worker.get("redis") or {}).get("prefix"):
            restated.append(f"{name}.redis.prefix")
        route = worker.get("sharedRoute") or {}
        if "gatewayName" in route:
            restated.append(f"{name}.sharedRoute.gatewayName")
        if "gatewayNamespace" in route:
            restated.append(f"{name}.sharedRoute.gatewayNamespace")
    assert not restated, restated


def test_uat21_quant_has_no_qdrant_env():
    extra = _values()["quant"].get("extraEnv") or []
    names = [row.get("name") for row in extra]
    assert "QDRANT_COLLECTION" not in names


def test_uat21_dockerfile_from_matches_chart_tag():
    tag = str(_values()["desk"]["image"]["tag"])
    desk_from = (ROOT / "images" / "example-finserve" / "Dockerfile").read_text()
    coder_from = (ROOT / "images" / "example-finserve-coder" / "Dockerfile").read_text()
    desk_pin = re.search(r"zelkor-aegra:([0-9]+\.[0-9]+\.[0-9]+)", desk_from)
    coder_pin = re.search(r"zelkor-aegra-deep:([0-9]+\.[0-9]+\.[0-9]+)", coder_from)
    assert desk_pin, desk_from.splitlines()[0]
    assert coder_pin, coder_from.splitlines()[0]
    assert desk_pin.group(1) == tag
    assert coder_pin.group(1) == tag
