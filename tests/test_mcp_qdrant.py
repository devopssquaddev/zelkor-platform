import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mcp"))

from tests.helpers.mcp_client import MCPGatewayClient
from wrappers.qdrant_server import QdrantMCPServer, stamp_upsert_payload


def test_upsert_document_forces_payload_tenant_id():
    payload = stamp_upsert_payload({"tenant_id": "tenant_b", "source": "model"}, "secret memo", "tenant_a")
    assert payload["tenant_id"] == "tenant_a"
    assert payload["document"] == "secret memo"
    assert payload["source"] == "model"


def test_qdrant_lists_upsert_not_inner_store():
    names = [t["name"] for t in QdrantMCPServer().list_tools()]
    assert "upsert_document" in names
    assert "search_documents" in names
    assert "qdrant-store" not in names


def test_mcp_qdrant_rejects_stray_tenant_id():
    """qdrant__search_documents rejects tenant_id in tool arguments."""
    client = MCPGatewayClient("tenant_a")
    try:
        with pytest.raises(RuntimeError, match="(?i)tenant_id"):
            client.call_tool(
                "qdrant__search_documents",
                {"query": "search documents", "tenant_id": "tenant_b"},
            )
    except ConnectionError as exc:
        pytest.skip(str(exc))


def test_mcp_qdrant_search_does_not_leak_other_tenant():
    """Search without a caller-supplied filter still cannot return another tenant's points."""
    client = MCPGatewayClient("tenant_a")
    try:
        result = client.call_tool(
            "qdrant__search_documents",
            {"query": "anything", "limit": 10},
        )
    except ConnectionError as exc:
        pytest.skip(str(exc))
    for doc in result.get("documents") or []:
        assert doc.get("tenant_id") == "tenant_a"


def test_mcp_qdrant_upsert_rejects_stray_tenant_id():
    client = MCPGatewayClient("tenant_a")
    try:
        with pytest.raises(RuntimeError, match="(?i)tenant_id"):
            client.call_tool(
                "qdrant__upsert_document",
                {"content": "should fail", "tenant_id": "tenant_b"},
            )
    except ConnectionError as exc:
        pytest.skip(str(exc))


def test_mcp_qdrant_upsert_then_search_does_not_leak_other_tenant():
    token = f"zelkor-upsert-{uuid.uuid4().hex[:12]}"
    writer = MCPGatewayClient("tenant_b")
    reader = MCPGatewayClient("tenant_a")
    try:
        stored = writer.call_tool(
            "qdrant__upsert_document",
            {"content": token, "metadata": {"tenant_id": "tenant_a"}},
        )
    except ConnectionError as exc:
        pytest.skip(str(exc))
    except RuntimeError as exc:
        if "embedding" in str(exc).lower() or "unavailable" in str(exc).lower():
            pytest.skip(str(exc))
        raise
    assert stored.get("tenant_id") == "tenant_b"
    leaked = reader.call_tool("qdrant__search_documents", {"query": token, "limit": 10})
    for doc in leaked.get("documents") or []:
        assert doc.get("tenant_id") == "tenant_a"
        blob = str(doc)
        assert token not in blob
    own = writer.call_tool("qdrant__search_documents", {"query": token, "limit": 10})
    assert any(token in str(doc) for doc in (own.get("documents") or []))
