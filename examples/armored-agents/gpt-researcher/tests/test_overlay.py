"""Render gpt-researcher overlay; live smoke is env-gated."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[4]
AGENT_CHART = ROOT / "charts" / "zelkor-agent"
VALUES = Path(__file__).resolve().parents[1] / "values.yaml"


def _helm(*extra: str) -> str:
    cmd = [
        "helm",
        "template",
        "gpt-researcher",
        str(AGENT_CHART),
        "-f",
        str(VALUES),
        "--set",
        "platform.releaseName=zelkor-platform",
        "--set",
        "sharedRoute.host=agents.example.com",
        "--set",
        "auth.issuer=https://issuer.example",
        "--set",
        "auth.audiences[0]=zelkor",
        *extra,
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        pytest.skip("helm not installed")
    if res.returncode != 0:
        pytest.fail(res.stderr or res.stdout)
    return res.stdout


def _docs(rendered: str) -> list:
    return [d for d in yaml.safe_load_all(rendered) if d]


def test_overlay_render_gvisor_clusterip():
    docs = _docs(_helm())
    svc = next(d for d in docs if d.get("kind") == "Service")
    deploy = next(d for d in docs if d.get("kind") == "Deployment")
    assert svc["spec"]["type"] == "ClusterIP"
    spec = deploy["spec"]["template"]["spec"]
    assert spec["runtimeClassName"] == "gvisor"
    dumped = yaml.dump(docs)
    assert "localhost" not in dumped
    assert "dev-key" not in dumped
    assert "sk-" not in dumped
    env = {e["name"]: e.get("value") for e in spec["containers"][0]["env"]}
    assert "AEGRA_CONFIG" not in env


def test_values_yaml_has_no_secrets_or_kind_hosts():
    text = VALUES.read_text(encoding="utf-8")
    assert "localhost" not in text
    assert "dev-key" not in text
    assert "TAVILY" not in text
    tools = Path(__file__).resolve().parents[1] / "tools.json"
    assert '"name": "tavily"' in tools.read_text(encoding="utf-8")
    assert "runtimeClassName: gvisor" in text
    assert 'aegraConfig: ""' in text or "aegraConfig: ''" in text


@pytest.mark.skipif(os.getenv("ARMOR_AGENT") != "gpt-researcher", reason="opt-in live armor smoke")
def test_live_skipped_without_agents_url():
    if not (os.getenv("ZELKOR_AGENTS_URL") or os.getenv("GATEWAY_BASE_URL")):
        pytest.skip("set ZELKOR_AGENTS_URL or GATEWAY_BASE_URL for live zelkor run")
