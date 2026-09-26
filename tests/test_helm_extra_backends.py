"""Helm render tests for workspace.tools.extraBackends compiler."""
from __future__ import annotations

import json

import yaml

from tests.test_helm_values_schema import CHART, SECRET_SETS, _docs, _helm


def _gateway_deploy(docs: list[dict]) -> dict:
    for doc in docs:
        if doc.get("kind") != "Deployment":
            continue
        if doc.get("metadata", {}).get("name", "").endswith("-mcp-gateway"):
            return doc
    raise AssertionError("mcp-gateway Deployment not found")


def test_extra_backend_compiled_json_has_no_secret_values():
    r = _helm(
        "--set",
        "workspace.tools.extraBackends[0].name=acme",
        "--set",
        "workspace.tools.extraBackends[0].url=http://acme-mcp:8080",
        "--set",
        "workspace.tools.extraBackends[0].auth.type=bearer",
        "--set",
        "workspace.tools.extraBackends[0].auth.secretRef.name=acme-secret",
        "--set",
        "workspace.tools.extraBackends[0].auth.secretRef.key=token",
    )
    assert r.returncode == 0, r.stderr
    dep = _gateway_deploy(_docs(r.stdout))
    env = {e["name"]: e for e in dep["spec"]["template"]["spec"]["containers"][0]["env"]}
    raw = env["MCP_EXTRA_BACKENDS"]["value"]
    assert "acme-secret" not in raw
    parsed = json.loads(raw)
    assert parsed[0]["name"] == "acme"
    assert parsed[0]["auth"]["type"] == "bearer"
    assert "bearerEnv" in parsed[0]["auth"]
    assert any(e["name"].startswith("ZELKOR_XB_") for e in dep["spec"]["template"]["spec"]["containers"][0]["env"] if "valueFrom" in e)


def test_external_url_requires_egress_cidrs_when_network_policies_enabled():
    r = _helm(
        "--set",
        "security.networkPolicies.enabled=true",
        "--set",
        "workspace.tools.extraBackends[0].name=saas",
        "--set",
        "workspace.tools.extraBackends[0].url=https://mcp.example.com",
    )
    assert r.returncode != 0
    assert "egress.cidrs" in r.stderr


def test_external_url_ipblock_when_egress_set():
    r = _helm(
        "--set",
        "security.networkPolicies.enabled=true",
        "--set",
        "workspace.tools.extraBackends[0].name=saas",
        "--set",
        "workspace.tools.extraBackends[0].url=https://mcp.example.com",
        "--set",
        "workspace.tools.extraBackends[0].egress.cidrs[0]=203.0.113.0/24",
    )
    assert r.returncode == 0, r.stderr
    nps = [d for d in _docs(r.stdout) if d.get("kind") == "NetworkPolicy"]
    gw_np = next(d for d in nps if d["metadata"]["name"].endswith("-mcp-gateway-egress"))
    blocks = [
        rule
        for rule in gw_np["spec"]["egress"]
        if rule.get("to") and rule["to"][0].get("ipBlock")
    ]
    assert any(b["to"][0]["ipBlock"]["cidr"] == "203.0.113.0/24" for b in blocks)


def test_extra_projects_missing_keys_fail_render():
    r = _helm(
        "--set",
        "platform.telemetry.langfuse.extraProjects[0].name=team-a",
    )
    assert r.returncode != 0
    assert "extraProjects" in r.stderr
