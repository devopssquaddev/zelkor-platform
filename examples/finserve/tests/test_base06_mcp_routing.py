import json
import os

import httpx
import pytest

GATEWAY_BASE_URL = os.environ.get("GATEWAY_BASE_URL", "http://127.0.0.1:8088")
MCP_HOST_HEADER = os.environ.get("MCP_HOST_HEADER", "mcp.localhost")


def test_mcp_gateway_tools_list():
    """Smoke test: unified MCP gateway exposes prefixed tools."""
    url = f"{GATEWAY_BASE_URL}/mcp"
    headers = {
        "Host": MCP_HOST_HEADER,
        "Content-Type": "application/json",
        "Authorization": "Bearer dev:Bank_Alpha",
        "X-Tenant-ID": "Bank_Alpha",
    }
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    try:
        resp = httpx.post(url, headers=headers, json=payload, timeout=10.0)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        tools = (data.get("result") or {}).get("tools") or []
        names = [t.get("name") for t in tools]
        assert any("postgres__" in n for n in names), f"Expected postgres tools, got {names}"
        assert any("qdrant__" in n for n in names), f"Expected qdrant tools, got {names}"
        assert any("sandbox__" in n for n in names), f"Expected sandbox tools, got {names}"
    except httpx.ConnectError:
        pytest.skip(f"Gateway not reachable at {GATEWAY_BASE_URL}")
