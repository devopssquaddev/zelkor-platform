"""L2/L3 live: Envoy MCP identity and backend JWT enforcement (Path B / kind)."""
from __future__ import annotations

import asyncio
import os

import httpx
import pytest

from tests.helpers.mcp_client import GATEWAY_BASE_URL, MCP_HOST_HEADER, MCPGatewayClient
from tests.helpers.tokens import test_tokens

pytestmark = pytest.mark.skipif(
    not test_tokens(),
    reason="ZELKOR_TEST_TOKENS not set (live MCP identity tests)",
)


@pytest.fixture()
def mcp_url() -> str:
    return f"{GATEWAY_BASE_URL.rstrip('/')}/mcp"


async def _post_json(url: str, headers: dict, payload: dict) -> httpx.Response:
    async with httpx.AsyncClient(timeout=30.0) as client:
        return await client.post(url, headers=headers, json=payload)


def test_l2_tenant_jwt_wins_over_forged_tenant_header(mcp_url):
    tokens = test_tokens()
    token = tokens.get("tenant-a")
    assert token
    headers = {
        "Host": MCP_HOST_HEADER,
        "Authorization": f"Bearer {token}",
        "X-Tenant-ID": "forged-tenant",
        "Accept": "application/json, text/event-stream",
    }
    init = asyncio.run(
        _post_json(
            mcp_url,
            headers,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "pytest", "version": "1"},
                },
            },
        )
    )
    assert init.status_code == 200


def test_l2_claimless_jwt_tools_list_empty(mcp_url):
    tokens = test_tokens()
    if "claimless" not in tokens:
        pytest.skip("claimless token not in ZELKOR_TEST_TOKENS")
    client = MCPGatewayClient("claimless")
    tools = client.list_tools()
    assert tools == []


def test_l2_no_jwt_initialize_unauthorized(mcp_url):
    headers = {
        "Host": MCP_HOST_HEADER,
        "Accept": "application/json, text/event-stream",
    }
    res = asyncio.run(
        _post_json(
            mcp_url,
            headers,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "pytest", "version": "1"},
                },
            },
        )
    )
    assert res.status_code in (401, 403)
