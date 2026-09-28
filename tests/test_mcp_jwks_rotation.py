"""L12 live: JWKS rotation accepted without pod restart (Path B only)."""
from __future__ import annotations

import asyncio
import os
import time

import httpx
import pytest

from tests.helpers.mcp_client import GATEWAY_BASE_URL, MCP_HOST_HEADER
from tests.helpers.tokens import test_tokens

pytestmark = [
    pytest.mark.skipif(
        not os.environ.get("ZELKOR_TEST_ROTATION"),
        reason="ZELKOR_TEST_ROTATION not set (internal/dev/ Path B rotation fixture)",
    ),
    pytest.mark.skipif(not test_tokens(), reason="ZELKOR_TEST_TOKENS not set"),
]


def _mcp_url() -> str:
    return f"{GATEWAY_BASE_URL.rstrip('/')}/mcp"


async def _initialize(token: str) -> httpx.Response:
    headers = {
        "Host": MCP_HOST_HEADER,
        "Authorization": f"Bearer {token}",
        "Accept": "application/json, text/event-stream",
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        return await client.post(
            _mcp_url(),
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "pytest-l12", "version": "1"},
                },
            },
        )


def _aegra_search(token: str) -> httpx.Response:
    host = os.environ.get("AGENTS_HOST_HEADER") or os.environ.get("AEGRA_HOST_HEADER") or ""
    if not host:
        pytest.skip("AGENTS_HOST_HEADER unset")
    headers = {
        "Host": host,
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    return httpx.post(
        f"{GATEWAY_BASE_URL.rstrip('/')}/assistants/search",
        headers=headers,
        json={},
        timeout=30.0,
    )


def _wait_status(fn, want: tuple[int, ...], timeout_s: float = 300.0) -> httpx.Response:
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        last = fn()
        if last.status_code in want:
            return last
        time.sleep(10)
    assert last is not None
    return last


def test_l12_rotation_key2_token_accepted():
    tokens = test_tokens()
    token = tokens.get("rotation-key-2")
    assert token, "rotation-key-2 missing in ZELKOR_TEST_TOKENS"
    res = _wait_status(lambda: asyncio.run(_initialize(token)), (200,))
    assert res.status_code == 200, res.text[:300]
    aegra = _wait_status(lambda: _aegra_search(token), (200,))
    assert aegra.status_code == 200, aegra.text[:300]


def test_l12_rotation_key1_still_valid_until_removed():
    tokens = test_tokens()
    token = tokens.get("rotation-key-1")
    assert token, "rotation-key-1 missing in ZELKOR_TEST_TOKENS"
    res = asyncio.run(_initialize(token))
    assert res.status_code == 200, res.text[:300]
    aegra = _aegra_search(token)
    assert aegra.status_code == 200, aegra.text[:300]


def test_l12_removed_key1_rejected_when_marked():
    tokens = test_tokens()
    token = tokens.get("rotation-key-1-removed")
    if not token:
        pytest.skip("rotation-key-1-removed not in ZELKOR_TEST_TOKENS (key-1 still in JWKS)")
    res = asyncio.run(_initialize(token))
    assert res.status_code in (401, 403), res.text[:300]
