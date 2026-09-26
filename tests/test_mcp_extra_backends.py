"""Unit tests for mcp.extraBackends merge (no cluster, no chart fixtures)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mcp"))

from gateway.backend_config import (  # noqa: E402
    RESERVED_PREFIXES,
    build_outbound_headers,
    merge_backends,
    parse_extra_backend_item,
    parse_extra_backends,
    validate_extra_name,
)
from gateway.gateway_server import native_backends  # noqa: E402


def test_native_backends_include_egress_when_url_set(monkeypatch):
    monkeypatch.setattr("gateway.gateway_server.POSTGRES_MCP_URL", "http://mcp-postgres:8080")
    monkeypatch.setattr("gateway.gateway_server.EGRESS_MCP_URL", "http://mcp-egress:8080")
    backends = native_backends()
    assert backends["egress"] == "http://mcp-egress:8080"
    assert backends["postgres"] == "http://mcp-postgres:8080"


def test_native_backends_omit_egress_when_unset(monkeypatch):
    monkeypatch.setattr("gateway.gateway_server.EGRESS_MCP_URL", "")
    assert "egress" not in native_backends()


def test_native_backends_omit_postgres_and_qdrant_when_unset(monkeypatch):
    monkeypatch.setattr("gateway.gateway_server.POSTGRES_MCP_URL", "")
    monkeypatch.setattr("gateway.gateway_server.QDRANT_MCP_URL", "")
    monkeypatch.setattr("gateway.gateway_server.SANDBOX_MCP_URL", "")
    monkeypatch.setattr("gateway.gateway_server.EGRESS_MCP_URL", "")
    assert native_backends() == {}


def test_native_backends_omit_sandbox_when_unset(monkeypatch):
    monkeypatch.setattr("gateway.gateway_server.SANDBOX_MCP_URL", "")
    assert "sandbox" not in native_backends()


def test_native_backends_include_sandbox_when_url_set(monkeypatch):
    monkeypatch.setattr("gateway.gateway_server.SANDBOX_MCP_URL", "http://mcp-sandbox:8080")
    assert native_backends()["sandbox"] == "http://mcp-sandbox:8080"


def test_parse_extra_backends_empty():
    assert parse_extra_backends("") == []
    assert parse_extra_backends("[]") == []


def test_merge_extra_backend_prefixes():
    native = {"postgres": "http://pg:8080", "qdrant": "http://qd:8080", "sandbox": "http://sb:8080"}
    extra = [parse_extra_backend_item({"name": "acme-tools", "url": "http://acme-mcp.acme-tools.svc:8080"})]
    merged = merge_backends(native, extra)
    assert merged["acme-tools"].url == "http://acme-mcp.acme-tools.svc:8080"
    assert merged["postgres"].url == "http://pg:8080"


@pytest.mark.parametrize("name", sorted(RESERVED_PREFIXES))
def test_reject_reserved_extra_backend_name(name):
    with pytest.raises(ValueError, match="reserved"):
        validate_extra_name(name)


def test_reject_double_underscore_in_name():
    with pytest.raises(ValueError, match="__"):
        validate_extra_name("foo__bar")


def test_reject_missing_url():
    with pytest.raises(ValueError, match="url"):
        parse_extra_backend_item({"name": "okname", "url": ""})


def test_bearer_auth_does_not_forward_zelkor_jwt(monkeypatch):
    monkeypatch.setenv("ZELKOR_XB_TOKEN", "saas-secret")
    cfg = parse_extra_backend_item(
        {
            "name": "saas",
            "url": "https://mcp.example.com",
            "auth": {"type": "bearer", "bearerEnv": "ZELKOR_XB_TOKEN"},
        }
    )
    hdrs = build_outbound_headers(cfg, {"Authorization": "Bearer tenant-jwt", "X-Tenant-ID": "tenant-a"})
    assert hdrs["Authorization"] == "Bearer saas-secret"
    assert "tenant-jwt" not in hdrs["Authorization"]


def test_inject_tenant_arg_off():
    cfg = parse_extra_backend_item(
        {"name": "saas", "url": "http://mcp:8080", "injectTenantArg": False}
    )
    assert cfg.inject_tenant_arg is False


def test_legacy_json_list_still_parses():
    raw = '[{"name": "acme", "url": "http://acme:8080"}]'
    items = parse_extra_backends(raw)
    assert len(items) == 1
    assert items[0].name == "acme"
