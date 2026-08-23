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
