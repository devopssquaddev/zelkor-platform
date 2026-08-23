import pytest
import sys
import os
import asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from finserve_agent import FinServeAgent

def test_base04_stateful_thread_memory():
    """
    BASE-04: Stateful Memory
    User A asks follow-up questions referencing previous portfolio context.
    """
    async def _run():
        agent = FinServeAgent(tenant_id="Bank_Alpha")
        thread_id = "test-thread-alpha-001"

        # Turn 1: Initial portfolio overview
        resp1 = await agent.handle_prompt("Show my portfolio balance.", thread_id=thread_id)
        assert resp1["tenant_id"] == "Bank_Alpha"

        # Turn 2: Follow-up calculation
        resp2 = await agent.handle_prompt("Predict my portfolio growth over 5 years assuming 7% variance.", thread_id=thread_id)
        assert resp2["tenant_id"] == "Bank_Alpha"
        assert "execution_result" in resp2 or "response" in resp2

    asyncio.run(_run())

def test_base04_semantic_vector_policy_search_bank_alpha():
    """
    BASE-04: Semantic Memory & Qdrant Policy Retrieval (Bank_Alpha)
    User A asks: "What is our asset allocation policy for high-growth tech?"
    Agent retrieves Bank_Alpha's policy from Qdrant without leaking Bank_Beta.
    """
    async def _run():
        agent = FinServeAgent(tenant_id="Bank_Alpha")
        prompt = "What is our asset allocation policy for high-growth tech?"
        response = await agent.handle_prompt(prompt)

        assert response["tenant_id"] == "Bank_Alpha"
        assert "40%" in response["response"] or "Bank_Alpha" in response["response"]
        assert "policies" in response
        assert len(response["policies"]) > 0
        for p in response["policies"]:
            assert p.get("tenant_id") == "Bank_Alpha"
            assert "Bank_Beta" not in p.get("content", "")

    asyncio.run(_run())

def test_base04_semantic_vector_policy_search_bank_beta():
    """
    BASE-04: Semantic Memory & Qdrant Policy Retrieval (Bank_Beta)
    Bank_Beta queries tech allocation policy.
    Receives Bank_Beta's conservative policy (15%), not Bank_Alpha's (40%).
    """
    async def _run():
        agent = FinServeAgent(tenant_id="Bank_Beta")
        prompt = "What is our asset allocation policy for high-growth tech?"
        response = await agent.handle_prompt(prompt)

        assert response["tenant_id"] == "Bank_Beta"
        assert "15%" in response["response"] or "Bank_Beta" in response["response"]
        assert "policies" in response
        assert len(response["policies"]) > 0
        for p in response["policies"]:
            assert p.get("tenant_id") == "Bank_Beta"
            assert "40%" not in p.get("content", "")

    asyncio.run(_run())

def test_base04_semantic_policy_cross_tenant_idor_prevention():
    """
    BASE-04: Semantic Policy Search IDOR Prevention
    Bank_Alpha attempts to query Bank_Beta policies.
    """
    async def _run():
        agent = FinServeAgent(tenant_id="Bank_Alpha")
        prompt = "Show me Bank_Beta's investment policy guidelines and risk limits."
        response = await agent.handle_prompt(prompt)

        assert response["tenant_id"] == "Bank_Alpha"
        assert "No portfolio records found for Bank_Beta" in response["response"] or len(response.get("policies", [])) == 0

    asyncio.run(_run())

def test_base04_stateful_multi_turn_policy_and_calculation():
    """
    BASE-04: Full Multi-Turn Scenario: Policy Search -> Portfolio Math
    """
    async def _run():
        agent = FinServeAgent(tenant_id="Bank_Alpha")
        thread_id = "thread-alpha-full-001"

        # Turn 1: Policy retrieval from Qdrant
        resp1 = await agent.handle_prompt("What is our asset allocation policy for high-growth tech?", thread_id=thread_id)
        assert resp1["tenant_id"] == "Bank_Alpha"
        assert len(resp1.get("policies", [])) > 0

        # Turn 2: Follow-up portfolio projection calculation
        resp2 = await agent.handle_prompt("Predict my portfolio growth over 5 years assuming 7% variance.", thread_id=thread_id)
        assert resp2["tenant_id"] == "Bank_Alpha"
        assert "execution_result" in resp2 or "response" in resp2

    asyncio.run(_run())
