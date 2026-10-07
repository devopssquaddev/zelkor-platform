"""UAT-11 live object MCP. Skip unless OBJECT_MCP_ENABLED is set."""
from __future__ import annotations

import os
import uuid

import pytest

from tests.helpers.mcp_client import MCPGatewayClient

pytestmark = pytest.mark.skipif(
    os.environ.get("OBJECT_MCP_ENABLED", "").lower() not in {"1", "true", "yes"},
    reason="OBJECT_MCP_ENABLED is not set",
)


def _client(tenant: str) -> MCPGatewayClient:
    return MCPGatewayClient(tenant)


def _require_tools():
    client = _client("tenant-a")
    try:
        names = {tool["name"] for tool in client.list_tools()}
    except ConnectionError as exc:
        pytest.skip(str(exc))
    assert "object__write_text" in names
    assert "object__read_text" in names
    return client


def test_object_round_trip_range_and_list():
    client = _require_tools()
    key = f"notes/{uuid.uuid4().hex}.txt"
    text = "abcdefghij"
    written = client.call_tool(
        "object__write_text",
        {"key": key, "text": text, "content_type": "text/plain; charset=utf-8"},
    )
    assert written["key"] == key
    assert written["size"] == len(text.encode())
    first = client.call_tool(
        "object__read_text",
        {"key": key, "offset": 0, "length": 4},
    )
    assert first["key"] == key
    assert first["offset"] == 0
    assert first["length"] == 4
    assert first["text"] == "abcd"
    assert first["eof"] is False
    second = client.call_tool(
        "object__read_text",
        {"key": key, "offset": 4, "length": 100},
    )
    assert second["offset"] == 4
    assert second["text"] == "efghij"
    assert second["eof"] is True
    listed = client.call_tool("object__list", {"prefix": "notes/", "limit": 100})
    keys = [item["key"] for item in listed["keys"]]
    assert key in keys
    assert all(not item["key"].startswith("tenant-") for item in listed["keys"])
    stat = client.call_tool("object__stat", {"key": key})
    assert stat["key"] == key
    assert stat["size"] == len(text.encode())
    copy_key = f"notes/{uuid.uuid4().hex}.txt"
    copied = client.call_tool("object__copy", {"source": key, "key": copy_key})
    assert copied["key"] == copy_key


def test_object_delete_denied_by_default():
    client = _require_tools()
    with pytest.raises(RuntimeError, match="(?i)disabled|permission"):
        client.call_tool("object__delete", {"key": "notes/nope.txt"})


def test_object_tenant_isolation():
    _require_tools()
    key = f"private/{uuid.uuid4().hex}.txt"
    owner = _client("tenant-a")
    other = _client("tenant-b")
    try:
        owner.call_tool("object__write_text", {"key": key, "text": "secret-a"})
    except ConnectionError as exc:
        pytest.skip(str(exc))
    listed = other.call_tool("object__list", {"prefix": "private/"})
    assert key not in [item["key"] for item in listed["keys"]]
    for stolen in (key, f"../tenant-a/{key}", f"/{key}"):
        with pytest.raises(RuntimeError):
            other.call_tool("object__read_text", {"key": stolen, "offset": 0, "length": 32})
