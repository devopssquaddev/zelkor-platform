"""Live UAT-10: generic extra MCP (claim headers, no client Authorization)."""
from __future__ import annotations

import pytest

from tests.helpers.mcp_client import MCPGatewayClient


def _client() -> MCPGatewayClient:
    return MCPGatewayClient("tenant_a")


def test_extra_backend_tools_list_and_auth_oracle():
    client = _client()
    try:
        tools = client.list_tools()
    except ConnectionError as exc:
        pytest.skip(str(exc))
    names = [t.get("name") for t in tools]
    extras = [n for n in names if n and n.startswith("acme__")]
    if not extras:
        pytest.skip("workspace.tools.extraBackends not registered (no acme__* tools)")
    assert any(n.startswith("postgres__") for n in names), names
    ping = next(t for t in tools if t.get("name") == "acme__ping")
    props = (ping.get("inputSchema") or {}).get("properties") or {}
    assert "tenant_id" not in props
    result = client.call_tool("acme__ping", {})
    assert result.get("ok") is True
    assert result.get("tenant_id")
    # Envoy may inject extra apiKey as Authorization; client JWT must not appear.
    assert result.get("authorization_is_jwt") is False
    with pytest.raises(Exception) as exc:
        client.call_tool("acme__ping", {"tenant_id": "spoof"})
    assert "tenant_id" in repr(exc.value)
