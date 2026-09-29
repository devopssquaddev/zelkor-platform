"""Unit tests for the generic extra echo MCP."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mcp"))

from wrappers.echo_server import EchoMCPServer, extract_extra_tenant


def test_echo_extracts_claim_header_not_authorization():
    assert extract_extra_tenant({"X-Tenant-ID": "tenant-a", "Authorization": "Bearer x"}) == "tenant-a"
    assert extract_extra_tenant({"authorization": "Bearer x"}) is None


def test_echo_schema_omits_tenant_id_and_reports_auth_flag():
    srv = EchoMCPServer()
    tools = srv.list_tools()
    assert tools[0]["name"] == "ping"
    assert "tenant_id" not in (tools[0]["inputSchema"].get("properties") or {})
    extract_extra_tenant({"x-tenant-id": "tenant-a"})
    out = srv.call_tool("ping", {}, "tenant-a")
    assert out["has_authorization"] is False
    assert out["authorization_is_jwt"] is False
    extract_extra_tenant({"x-tenant-id": "tenant-a", "Authorization": "Bearer eyJhbGciOiJSUzI1NiJ9.e30.sig"})
    out = srv.call_tool("ping", {}, "tenant-a")
    assert out["authorization_is_jwt"] is True
