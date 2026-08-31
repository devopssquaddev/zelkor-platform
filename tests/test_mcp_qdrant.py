import pytest

from tests.helpers.mcp_client import MCPGatewayClient


def test_mcp_qdrant_rejects_tenant_id_mismatch():
    """qdrant__search_documents rejects when tool arg tenant_id does not match auth header."""
    client = MCPGatewayClient("tenant_a")
    try:
        with pytest.raises(RuntimeError, match="tenant_id mismatch"):
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
