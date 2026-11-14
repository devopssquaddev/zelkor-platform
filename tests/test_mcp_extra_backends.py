"""Live UAT-10: generic extra MCP (claim headers, no client Authorization).

Works in either profile: the extra registered with the echo test server is found by its prefix
(MCP_EXTRA_BACKEND_PREFIX, default `acme`); skips when none is registered.
"""
from __future__ import annotations

import os

import pytest

from tests.helpers.mcp_client import MCPGatewayClient

PREFIX = os.environ.get("MCP_EXTRA_BACKEND_PREFIX", "acme").strip() + "__"


def _client() -> MCPGatewayClient:
    return MCPGatewayClient("tenant_a")


def test_extra_backend_tools_list_and_auth_oracle():
    client = _client()
    try:
        tools = client.list_tools()
    except ConnectionError as exc:
        pytest.skip(str(exc))
    names = [t.get("name") for t in tools]
    if f"{PREFIX}ping" not in names:
        pytest.skip(f"no echo extra registered ({PREFIX}ping not in tools/list)")
    ping = next(t for t in tools if t.get("name") == f"{PREFIX}ping")
    props = (ping.get("inputSchema") or {}).get("properties") or {}
    assert "tenant_id" not in props
    result = client.call_tool(f"{PREFIX}ping", {})
    assert result.get("ok") is True
    assert result.get("tenant_id") == "tenant_a"
    # Envoy may inject extra apiKey as Authorization; client JWT must not appear.
    assert result.get("authorization_is_jwt") is False
    with pytest.raises(Exception) as exc:
        client.call_tool(f"{PREFIX}ping", {"tenant_id": "spoof"})
    assert "tenant_id" in repr(exc.value)
