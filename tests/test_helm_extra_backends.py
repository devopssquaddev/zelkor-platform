"""Helm render tests for workspace.tools.extraBackends on MCPRoute."""
from __future__ import annotations

import yaml

from tests.test_helm_values_schema import _docs, _helm


def _mcproute(docs: list[dict]) -> dict:
    routes = [d for d in docs if d.get("kind") == "MCPRoute"]
    assert len(routes) == 1, "expected one MCPRoute"
    return routes[0]


def test_extra_backend_appears_on_mcproute():
    r = _helm(
        "--set",
        "gateway.hosts.mcp=mcp.example.com",
        "--set",
        "platform.tenants.jwt.issuer=https://issuer.example",
        "--set",
        "platform.tenants.jwt.audiences[0]=zelkor",
        "--set",
        "workspace.tools.extraBackends[0].name=acme",
        "--set",
        "workspace.tools.extraBackends[0].service.name=acme-mcp",
        "--set",
        "workspace.tools.extraBackends[0].service.port=8080",
    )
    assert r.returncode == 0, r.stderr
    route = _mcproute(_docs(r.stdout))
    names = [ref.get("name") for ref in route["spec"].get("backendRefs") or []]
    assert "acme" in names


def test_external_fqdn_requires_egress_cidrs_when_network_policies_enabled():
    r = _helm(
        "--set",
        "security.networkPolicies.enabled=true",
        "--set",
        "gateway.hosts.mcp=mcp.example.com",
        "--set",
        "platform.tenants.jwt.issuer=https://issuer.example",
        "--set",
        "platform.tenants.jwt.audiences[0]=zelkor",
        "--set",
        "workspace.tools.extraBackends[0].name=saas",
        "--set",
        "workspace.tools.extraBackends[0].fqdn.hostname=mcp.example.com",
    )
    assert r.returncode != 0
    assert "egress.cidrs" in r.stderr


def test_extra_projects_missing_keys_fail_render():
    r = _helm(
        "--set",
        "platform.telemetry.langfuse.extraProjects[0].name=team-a",
    )
    assert r.returncode != 0
    assert "extraProjects" in r.stderr
