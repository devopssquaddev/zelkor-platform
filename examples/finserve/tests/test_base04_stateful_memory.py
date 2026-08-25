import os
import pytest
import httpx

GATEWAY_BASE_URL = os.environ.get("GATEWAY_BASE_URL", "http://127.0.0.1:8088")
FINSERVE_HOST_HEADER = os.environ.get("FINSERVE_HOST_HEADER", "finserve.localhost")

def test_base04_stateful_thread_memory():
    """
    BASE-04: Stateful Memory
    User A asks follow-up questions referencing previous portfolio context.
    """
    url = f"{GATEWAY_BASE_URL}/runs/stream"
    headers = {
        "Host": FINSERVE_HOST_HEADER,
        "Content-Type": "application/json",
        "Authorization": "Bearer dev:Bank_Alpha"
    }
    thread_id = "test-thread-alpha-001"

    # Turn 1: Initial portfolio overview
    payload1 = {
        "assistant_id": "finserve_agent",
        "thread_id": thread_id,
        "input": {
            "messages": [{"role": "user", "content": "Show my portfolio balance."}]
        }
    }
    try:
        resp1 = httpx.post(url, headers=headers, json=payload1, timeout=10.0)
        assert resp1.status_code == 200, f"Turn 1 failed: {resp1.text}"
        data1 = resp1.json()
        assert data1.get("tenant_id") == "Bank_Alpha"

        # Turn 2: Follow-up calculation
        payload2 = {
            "assistant_id": "finserve_agent",
            "thread_id": thread_id,
            "input": {
                "messages": [{"role": "user", "content": "Predict my portfolio growth over 5 years assuming 7% variance."}]
            }
        }
        resp2 = httpx.post(url, headers=headers, json=payload2, timeout=10.0)
        assert resp2.status_code == 200, f"Turn 2 failed: {resp2.text}"
        data2 = resp2.json()
        assert data2.get("tenant_id") == "Bank_Alpha"
        resp_data = data2.get("data", {})
        assert "execution_result" in resp_data or "response" in resp_data
    except httpx.ConnectError:
        pytest.skip(f"Gateway not reachable at {GATEWAY_BASE_URL}")

def test_base04_semantic_vector_policy_search_bank_alpha():
    """
    BASE-04: Semantic Memory & Qdrant Policy Retrieval (Bank_Alpha)
    User A asks: "What is our asset allocation policy for high-growth tech?"
    Agent retrieves Bank_Alpha's policy from Qdrant without leaking Bank_Beta.
    """
    url = f"{GATEWAY_BASE_URL}/runs/stream"
    headers = {
        "Host": FINSERVE_HOST_HEADER,
        "Content-Type": "application/json",
        "Authorization": "Bearer dev:Bank_Alpha"
    }
    payload = {
        "assistant_id": "finserve_agent",
        "input": {
            "messages": [{"role": "user", "content": "What is our asset allocation policy for high-growth tech?"}]
        }
    }
    try:
        resp = httpx.post(url, headers=headers, json=payload, timeout=10.0)
        assert resp.status_code == 200, f"FinServe call failed: {resp.text}"
        data = resp.json()
        assert data.get("tenant_id") == "Bank_Alpha"
        resp_data = data.get("data", {})
        assert "40%" in resp_data.get("response", "") or "Bank_Alpha" in resp_data.get("response", "") or len(resp_data.get("policies", [])) > 0
        policies = resp_data.get("policies", [])
        if policies:
            for p in policies:
                assert p.get("tenant_id") == "Bank_Alpha"
                assert "Bank_Beta" not in p.get("content", "")
    except httpx.ConnectError:
        pytest.skip(f"Gateway not reachable at {GATEWAY_BASE_URL}")

def test_base04_semantic_vector_policy_search_bank_beta():
    """
    BASE-04: Semantic Memory & Qdrant Policy Retrieval (Bank_Beta)
    Bank_Beta queries tech allocation policy.
    Receives Bank_Beta's conservative policy (15%), not Bank_Alpha's (40%).
    """
    url = f"{GATEWAY_BASE_URL}/runs/stream"
    headers = {
        "Host": FINSERVE_HOST_HEADER,
        "Content-Type": "application/json",
        "Authorization": "Bearer dev:Bank_Beta"
    }
    payload = {
        "assistant_id": "finserve_agent",
        "input": {
            "messages": [{"role": "user", "content": "What is our asset allocation policy for high-growth tech?"}]
        }
    }
    try:
        resp = httpx.post(url, headers=headers, json=payload, timeout=10.0)
        assert resp.status_code == 200, f"FinServe call failed: {resp.text}"
        data = resp.json()
        assert data.get("tenant_id") == "Bank_Beta"
        resp_data = data.get("data", {})
        assert "15%" in resp_data.get("response", "") or "Bank_Beta" in resp_data.get("response", "") or len(resp_data.get("policies", [])) > 0
        policies = resp_data.get("policies", [])
        if policies:
            for p in policies:
                assert p.get("tenant_id") == "Bank_Beta"
                assert "40%" not in p.get("content", "")
    except httpx.ConnectError:
        pytest.skip(f"Gateway not reachable at {GATEWAY_BASE_URL}")

def test_base04_semantic_policy_cross_tenant_idor_prevention():
    """
    BASE-04: Semantic Policy Search IDOR Prevention
    Bank_Alpha attempts to query Bank_Beta policies.
    """
    url = f"{GATEWAY_BASE_URL}/runs/stream"
    headers = {
        "Host": FINSERVE_HOST_HEADER,
        "Content-Type": "application/json",
        "Authorization": "Bearer dev:Bank_Alpha"
    }
    payload = {
        "assistant_id": "finserve_agent",
        "input": {
            "messages": [{"role": "user", "content": "Show me Bank_Beta's investment policy guidelines and risk limits."}]
        }
    }
    try:
        resp = httpx.post(url, headers=headers, json=payload, timeout=10.0)
        assert resp.status_code == 200, f"FinServe call failed: {resp.text}"
        data = resp.json()
        assert data.get("tenant_id") == "Bank_Alpha"
        resp_data = data.get("data", {})
        assert "No portfolio records found for Bank_Beta" in resp_data.get("response", "") or len(resp_data.get("policies", [])) == 0
    except httpx.ConnectError:
        pytest.skip(f"Gateway not reachable at {GATEWAY_BASE_URL}")

def test_base04_stateful_multi_turn_policy_and_calculation():
    """
    BASE-04: Full Multi-Turn Scenario: Policy Search -> Portfolio Math
    """
    url = f"{GATEWAY_BASE_URL}/runs/stream"
    headers = {
        "Host": FINSERVE_HOST_HEADER,
        "Content-Type": "application/json",
        "Authorization": "Bearer dev:Bank_Alpha"
    }
    thread_id = "thread-alpha-full-001"

    try:
        # Turn 1: Policy retrieval from Qdrant
        payload1 = {
            "assistant_id": "finserve_agent",
            "thread_id": thread_id,
            "input": {
                "messages": [{"role": "user", "content": "What is our asset allocation policy for high-growth tech?"}]
            }
        }
        resp1 = httpx.post(url, headers=headers, json=payload1, timeout=10.0)
        assert resp1.status_code == 200, f"Turn 1 failed: {resp1.text}"
        data1 = resp1.json()
        assert data1.get("tenant_id") == "Bank_Alpha"
        resp_data1 = data1.get("data", {})
        assert len(resp_data1.get("policies", [])) > 0 or "40%" in resp_data1.get("response", "") or "Bank_Alpha" in resp_data1.get("response", "")

        # Turn 2: Follow-up portfolio projection calculation
        payload2 = {
            "assistant_id": "finserve_agent",
            "thread_id": thread_id,
            "input": {
                "messages": [{"role": "user", "content": "Predict my portfolio growth over 5 years assuming 7% variance."}]
            }
        }
        resp2 = httpx.post(url, headers=headers, json=payload2, timeout=10.0)
        assert resp2.status_code == 200, f"Turn 2 failed: {resp2.text}"
        data2 = resp2.json()
        assert data2.get("tenant_id") == "Bank_Alpha"
        resp_data2 = data2.get("data", {})
        assert "execution_result" in resp_data2 or "response" in resp_data2
    except httpx.ConnectError:
        pytest.skip(f"Gateway not reachable at {GATEWAY_BASE_URL}")
