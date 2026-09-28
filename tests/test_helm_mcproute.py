"""C5: MCPRoute helm render (native refs, guards, no legacy gateway)."""
from __future__ import annotations

from pathlib import Path

from tests.test_helm_values_schema import PROFILES, _docs, _helm

INLINE_JWKS = Path(__file__).resolve().parent / "fixtures" / "lab-inline-jwks.yaml"


def _helm_local_jwks(*extra: str):
    return _helm(
        *extra,
        "--set",
        "platform.tenants.jwt.remoteJwksUri=",
        values_files=[INLINE_JWKS],
    )


def _mcproute(docs: list[dict]) -> dict:
    routes = [d for d in docs if d.get("kind") == "MCPRoute"]
    assert len(routes) == 1, f"expected one MCPRoute, got {[d['metadata']['name'] for d in routes]}"
    return routes[0]


def _native_backend_refs(route: dict) -> list[dict]:
    return [ref for ref in route["spec"].get("backendRefs") or [] if ref.get("forwardHeaders")]


def test_mcproute_absent_when_tools_disabled():
    r = _helm("--set", "workspace.tools.enabled=false")
    assert r.returncode == 0, r.stderr
    assert not [d for d in _docs(r.stdout) if d.get("kind") == "MCPRoute"]


def test_mcproute_requires_gateway_or_parent_ref():
    r = _helm("--set", "gateway.enabled=false", "--set", "gateway.parentRef.name=")
    assert r.returncode != 0
    assert "MCPRoute" in r.stderr or "gateway" in r.stderr


def test_native_backends_forward_authorization_only():
    r = _helm()
    assert r.returncode == 0, r.stderr
    route = _mcproute(_docs(r.stdout))
    natives = _native_backend_refs(route)
    assert len(natives) >= 4
    for ref in natives:
        headers = [h.get("name") if isinstance(h, dict) else h for h in ref.get("forwardHeaders") or []]
        assert headers == ["Authorization"]
        assert ref.get("group") == "gateway.envoyproxy.io"
        assert ref.get("kind") == "Backend"


def test_native_ref_kind_service_uses_clusterip_names():
    r = _helm("--set", "gateway.mcproute.nativeRefKind=Service")
    assert r.returncode == 0, r.stderr
    route = _mcproute(_docs(r.stdout))
    for ref in _native_backend_refs(route):
        assert ref.get("kind") == "Service"
        assert ref["name"].startswith("zelkor-platform-mcp-")
        assert ref.get("group") in (None, "")


def test_extra_backend_ref_has_no_authorization_forward():
    r = _helm(
        "--set",
        "workspace.tools.extraBackends[0].name=acme",
        "--set",
        "workspace.tools.extraBackends[0].service.name=acme-mcp",
        "--set",
        "workspace.tools.extraBackends[0].service.port=8080",
    )
    assert r.returncode == 0, r.stderr
    route = _mcproute(_docs(r.stdout))
    acme = next(ref for ref in route["spec"]["backendRefs"] if ref.get("name") == "acme")
    assert "forwardHeaders" not in acme or not acme.get("forwardHeaders")


def test_mcproute_local_jwks_when_no_remote_uri():
    r = _helm_local_jwks()
    assert r.returncode == 0, r.stderr
    route = _mcproute(_docs(r.stdout))
    jwks = route["spec"]["securityPolicy"]["oauth"]["jwks"]
    assert "localJWKS" in jwks
    assert jwks["localJWKS"]["valueRef"]["name"] == "zelkor-platform-tenant-jwks"


def test_empty_mcp_hostname_uses_internal_dataplane_hostnames():
    r = _helm("--set", "gateway.hosts.mcp=")
    assert r.returncode == 0, r.stderr
    route = _mcproute(_docs(r.stdout))
    hostnames = route["spec"].get("hostnames") or []
    assert any("zelkor-platform-mcp" in h for h in hostnames)


def test_shared_gateway_requires_ack():
    r = _helm(
        "--set",
        "gateway.enabled=false",
        "--set",
        "gateway.parentRef.name=shared-gw",
        "--set",
        "gateway.parentRef.namespace=envoy-system",
        "--set",
        "gateway.envoyProxy.enabled=false",
        "--set",
        "workspace.models.inClusterService.enabled=true",
        "--set",
        "workspace.models.inClusterService.targetHost=envoy.example.svc",
        "--set",
        "security.mcp.acceptUnprotectedBackends=true",
    )
    assert r.returncode != 0
    assert "sharedGatewayAck" in r.stderr


def test_reserved_extra_backend_name_fails():
    r = _helm(
        "--set",
        "workspace.tools.extraBackends[0].name=postgres",
        "--set",
        "workspace.tools.extraBackends[0].service.name=x",
        "--set",
        "workspace.tools.extraBackends[0].service.port=8080",
    )
    assert r.returncode != 0
    assert "reserved" in r.stderr


def test_no_legacy_mcp_gateway_objects_in_profiles():
    for profile in PROFILES.glob("values*.yaml"):
        r = _helm(values_files=[profile])
        assert r.returncode == 0, f"{profile.name}: {r.stderr}"
        lowered = r.stdout.lower()
        assert "mcp-gateway" not in lowered
        assert "mcp_gateway" not in lowered
