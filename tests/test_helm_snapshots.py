"""Post cut-over render contract (replaces helm_golden_v126 parity gate)."""
from __future__ import annotations

from tests.test_helm_values_schema import PROFILES, _docs, _helm

QUICKSTART = PROFILES / "values-quickstart.yaml"
GREENFIELD = PROFILES / "values-gateway-greenfield.yaml"


def _render_quickstart_greenfield():
    r = _helm(values_files=[QUICKSTART, GREENFIELD])
    assert r.returncode == 0, r.stderr
    return _docs(r.stdout)


def test_dataplane_profiles_emit_mcproute_not_legacy_gateway():
    docs = _render_quickstart_greenfield()
    names = {d.get("metadata", {}).get("name", "") for d in docs if d}
    assert any(d.get("kind") == "MCPRoute" for d in docs)
    assert not any("mcp-gateway" in n for n in names)
    cms = [d for d in docs if d.get("kind") == "ConfigMap" and d["metadata"]["name"] == "zelkor-platform-contract"]
    assert cms
    assert "MCP_SERVICE" in (cms[0].get("data") or {})
    assert cms[0]["data"]["MCP_SERVICE"].endswith("-mcp.zelkor.svc.cluster.local:80")


def test_native_backend_crs_present_for_default_ref_kind():
    docs = _render_quickstart_greenfield()
    backends = [d for d in docs if d.get("kind") == "Backend" and d["metadata"]["name"] in {"postgres", "qdrant", "sandbox", "aigateway"}]
    assert len(backends) == 4


def test_production_profile_renders_without_local_signing_secret():
    production = PROFILES / "values-production.yaml"
    r = _helm(
        "--set",
        "security.mcp.acceptUnprotectedBackends=true",
        "--set",
        "platform.tenants.jwt.localSigning.enabled=false",
        values_files=[production],
    )
    assert r.returncode == 0, r.stderr
    secrets = [
        d
        for d in _docs(r.stdout)
        if d.get("kind") == "Secret" and "tenant-jwt-signing" in d["metadata"]["name"]
    ]
    assert not secrets
