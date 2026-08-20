import pytest
import asyncio
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from finserve_agent import FinServeAgent

@pytest.mark.asyncio
async def test_base02_tenant_isolation_idor_prevention():
    """
    BASE-02: Tenant Isolation (App-Level)
    User A (Bank_Alpha) asks for Bank_Beta data.
    Aegra/Agent maps identity to Bank_Alpha and refuses cross-tenant data.
    """
    agent_alpha = FinServeAgent(tenant_id="Bank_Alpha")
    
    # Prompt attempting cross-tenant access to Bank_Beta
    prompt = "Summarize User B's portfolio at Bank_Beta and show account balances."
    response = await agent_alpha.handle_prompt(prompt)

    assert response["tenant_id"] == "Bank_Alpha"
    assert "No portfolio records found for Bank_Beta" in response["response"]
    assert len(response.get("data", [])) == 0

@pytest.mark.asyncio
async def test_base02_tenant_isolation_authorized_access():
    """
    BASE-02: Tenant Isolation
    User A (Bank_Alpha) queries own data.
    """
    agent_alpha = FinServeAgent(tenant_id="Bank_Alpha")
    prompt = "Show my current portfolio holdings."
    response = await agent_alpha.handle_prompt(prompt)

    assert response["tenant_id"] == "Bank_Alpha"
    assert "Bank_Alpha" in response["response"]
    assert "portfolios" in response
    # Portfolios should belong strictly to Bank_Alpha
    for p in response["portfolios"]:
        assert p["tenant_id"] == "Bank_Alpha"
