import pytest

from tests.helpers.mcp_client import MCPGatewayClient


def test_mcp_postgres_rejects_non_select():
    """postgres__query wrapper rejects mutating SQL."""
    client = MCPGatewayClient("tenant_a")
    try:
        with pytest.raises(RuntimeError, match="(?i)select|permitted"):
            client.call_tool(
                "postgres__query",
                {"sql": "DELETE FROM items WHERE id = 1"},
            )
    except ConnectionError as exc:
        pytest.skip(str(exc))


def test_mcp_postgres_rejects_tenant_id_mismatch():
    """postgres__query rejects when tool arg tenant_id does not match auth header."""
    client = MCPGatewayClient("tenant_a")
    try:
        with pytest.raises(RuntimeError, match="tenant_id mismatch"):
            client.call_tool(
                "postgres__query",
                {"sql": "SELECT 1 AS ok", "tenant_id": "tenant_b"},
            )
    except ConnectionError as exc:
        pytest.skip(str(exc))


def test_mcp_postgres_select_without_schema_assumptions():
    """postgres__query executes generic read-only SQL with no demo table names."""
    client = MCPGatewayClient("tenant_a")
    try:
        result = client.call_tool("postgres__query", {"sql": "SELECT 1 AS ok"})
    except ConnectionError as exc:
        pytest.skip(str(exc))
    rows = result.get("rows") or []
    assert rows
    assert rows[0].get("ok") == 1


def test_mcp_postgres_list_tables_is_schema_agnostic():
    """postgres__list_tables returns grant-filtered relations, not a demo schema."""
    client = MCPGatewayClient("tenant_a")
    try:
        result = client.call_tool("postgres__list_tables", {})
    except ConnectionError as exc:
        pytest.skip(str(exc))
    assert "tables" in result
    assert isinstance(result["tables"], list)


def test_mcp_postgres_get_schema_rejects_unauthorized_relation():
    """postgres__get_schema rejects unknown or unauthorized relation names."""
    client = MCPGatewayClient("tenant_a")
    try:
        with pytest.raises(RuntimeError, match="(?i)unknown or unauthorized|mismatch"):
            client.call_tool(
                "postgres__get_schema",
                {"name": "pg_catalog.pg_shadow"},
            )
    except ConnectionError as exc:
        pytest.skip(str(exc))


def test_mcp_postgres_get_schema_rejects_tenant_mismatch():
    client = MCPGatewayClient("tenant_a")
    try:
        with pytest.raises(RuntimeError, match="tenant_id mismatch"):
            client.call_tool(
                "postgres__get_schema",
                {"name": "items", "tenant_id": "tenant_b"},
            )
    except ConnectionError as exc:
        pytest.skip(str(exc))


def test_mcp_postgres_rejects_multi_statement():
    client = MCPGatewayClient("tenant_a")
    try:
        with pytest.raises(RuntimeError, match="(?i)multiple"):
            client.call_tool(
                "postgres__query",
                {"sql": "SELECT 1; SELECT 2"},
            )
    except ConnectionError as exc:
        pytest.skip(str(exc))
