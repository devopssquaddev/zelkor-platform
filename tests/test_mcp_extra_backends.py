"""Unit tests for mcp.extraBackends merge (no cluster, no chart fixtures)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mcp"))

from gateway.gateway_server import (  # noqa: E402
    RESERVED_PREFIXES,
    merge_backends,
    native_backends,
    parse_extra_backends,
    validate_extra_name,
)


def test_native_backends_include_egress_when_url_set(monkeypatch):
    monkeypatch.setattr("gateway.gateway_server.EGRESS_MCP_URL", "http://mcp-egress:8080")
    backends = native_backends()
    assert backends["egress"] == "http://mcp-egress:8080"
    assert "postgres" in backends


def test_native_backends_omit_egress_when_unset(monkeypatch):
    monkeypatch.setattr("gateway.gateway_server.EGRESS_MCP_URL", "")
    assert "egress" not in native_backends()


def test_parse_extra_backends_empty():
    assert parse_extra_backends("") == []
    assert parse_extra_backends("[]") == []


def test_merge_extra_backend_prefixes():
    native = {"postgres": "http://pg:8080", "qdrant": "http://qd:8080", "sandbox": "http://sb:8080"}
    merged = merge_backends(
        native,
        [{"name": "acme-tools", "url": "http://acme-mcp.acme-tools.svc:8080"}],
    )
    assert merged["acme-tools"] == "http://acme-mcp.acme-tools.svc:8080"
    assert merged["postgres"] == "http://pg:8080"


@pytest.mark.parametrize("name", sorted(RESERVED_PREFIXES))
def test_reject_reserved_extra_backend_name(name):
    with pytest.raises(ValueError, match="reserved"):
        validate_extra_name(name)


def test_reject_double_underscore_in_name():
    with pytest.raises(ValueError, match="__"):
        validate_extra_name("foo__bar")


def test_reject_missing_url():
    with pytest.raises(ValueError, match="url"):
        merge_backends({}, [{"name": "okname", "url": ""}])
