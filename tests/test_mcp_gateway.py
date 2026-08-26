import os

import httpx
import pytest

GATEWAY_BASE_URL = os.environ.get("GATEWAY_BASE_URL", "http://127.0.0.1:8088")
MCP_HOST_HEADER = os.environ.get("MCP_HOST_HEADER", "mcp.localhost")


def test_platform_mcp_gateway_health():
    """Platform MCP gateway health via Gateway."""
    url = f"{GATEWAY_BASE_URL}/health"
    headers = {"Host": MCP_HOST_HEADER}
    try:
        resp = httpx.get(url, headers=headers, timeout=5.0)
        assert resp.status_code == 200
        assert resp.json().get("status") == "ok"
    except httpx.ConnectError:
        pytest.skip(f"Gateway not reachable at {GATEWAY_BASE_URL}")
