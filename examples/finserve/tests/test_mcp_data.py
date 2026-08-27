import pytest

from tests.helpers.mcp_client import MCPGatewayClient


def test_finserve_mcp_postgres_tenant_scoped_query():
    """postgres__query returns only rows for the authenticated tenant."""
    client = MCPGatewayClient("Bank_Alpha")
    try:
        result = client.call_tool(
            "postgres__query",
            {"sql": "SELECT * FROM portfolios WHERE tenant_id = %s"},
        )
    except ConnectionError as exc:
        pytest.skip(str(exc))

    rows = result.get("rows") or []
    assert len(rows) >= 1
    for row in rows:
        assert row.get("tenant_id") == "Bank_Alpha"
        assert isinstance(row.get("balance"), (int, float))


def test_finserve_mcp_postgres_bank_beta_isolation():
    """Bank_Beta tenant receives distinct portfolio data from Bank_Alpha."""
    alpha = MCPGatewayClient("Bank_Alpha")
    beta = MCPGatewayClient("Bank_Beta")
    try:
        alpha_rows = alpha.call_tool(
            "postgres__query",
            {"sql": "SELECT * FROM portfolios WHERE tenant_id = %s"},
        ).get("rows") or []
        beta_rows = beta.call_tool(
            "postgres__query",
            {"sql": "SELECT * FROM portfolios WHERE tenant_id = %s"},
        ).get("rows") or []
    except ConnectionError as exc:
        pytest.skip(str(exc))

    assert alpha_rows and beta_rows
    alpha_accounts = {r.get("account_number") for r in alpha_rows}
    beta_accounts = {r.get("account_number") for r in beta_rows}
    assert alpha_accounts.isdisjoint(beta_accounts)


def test_finserve_mcp_qdrant_bank_alpha_tech_policy():
    """qdrant__search_documents returns Bank_Alpha high-growth tech policy (40%)."""
    client = MCPGatewayClient("Bank_Alpha")
    try:
        result = client.call_tool(
            "qdrant__search_documents",
            {"query": "What is our asset allocation policy for high-growth tech?", "limit": 3},
        )
    except ConnectionError as exc:
        pytest.skip(str(exc))

    docs = result.get("documents") or []
    assert docs
    contents = " ".join(d.get("content", "") for d in docs)
    assert "40%" in contents or "High-Growth Tech" in contents
    for doc in docs:
        assert doc.get("tenant_id") == "Bank_Alpha"


def test_finserve_mcp_qdrant_bank_beta_conservative_policy():
    """Bank_Beta receives conservative tech allocation (15%), not Bank_Alpha 40%."""
    client = MCPGatewayClient("Bank_Beta")
    try:
        result = client.call_tool(
            "qdrant__search_documents",
            {"query": "What is our asset allocation policy for high-growth tech?", "limit": 3},
        )
    except ConnectionError as exc:
        pytest.skip(str(exc))

    docs = result.get("documents") or []
    assert docs
    contents = " ".join(d.get("content", "") for d in docs)
    assert "15%" in contents or "Bank_Beta" in contents
    assert "40%" not in contents
    for doc in docs:
        assert doc.get("tenant_id") == "Bank_Beta"
