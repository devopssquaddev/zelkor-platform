import os
import pytest
import httpx

GATEWAY_BASE_URL = os.environ.get("GATEWAY_BASE_URL", "http://127.0.0.1:8088")
FINSERVE_HOST_HEADER = os.environ.get("FINSERVE_HOST_HEADER", "finserve.localhost")


def test_base04_stateful_thread_memory():
    """E2E smoke: multi-turn thread requests succeed."""
    url = f"{GATEWAY_BASE_URL}/runs/stream"
    headers = {
        "Host": FINSERVE_HOST_HEADER,
        "Content-Type": "application/json",
        "Authorization": "Bearer dev:Bank_Alpha",
    }
    thread_id = "test-thread-alpha-smoke-001"

    try:
        resp1 = httpx.post(
            url,
            headers=headers,
            json={
                "assistant_id": "finserve_agent",
                "thread_id": thread_id,
                "input": {"messages": [{"role": "user", "content": "Show my portfolio balance."}]},
            },
            timeout=60.0,
        )
        assert resp1.status_code == 200, f"Turn 1 failed: {resp1.text}"
        assert resp1.json().get("tenant_id") == "Bank_Alpha"

        resp2 = httpx.post(
            url,
            headers=headers,
            json={
                "assistant_id": "finserve_agent",
                "thread_id": thread_id,
                "input": {
                    "messages": [{
                        "role": "user",
                        "content": "What is our asset allocation policy for high-growth tech?",
                    }]
                },
            },
            timeout=60.0,
        )
        assert resp2.status_code == 200, f"Turn 2 failed: {resp2.text}"
        data2 = resp2.json().get("data", {})
        assert data2.get("response")
    except httpx.ConnectError:
        pytest.skip(f"Gateway not reachable at {GATEWAY_BASE_URL}")


def test_base04_policy_query_smoke():
    """E2E smoke: on-topic policy query returns structured agent response."""
    url = f"{GATEWAY_BASE_URL}/runs/stream"
    headers = {
        "Host": FINSERVE_HOST_HEADER,
        "Content-Type": "application/json",
        "Authorization": "Bearer dev:Bank_Alpha",
    }
    try:
        resp = httpx.post(
            url,
            headers=headers,
            json={
                "assistant_id": "finserve_agent",
                "input": {
                    "messages": [{
                        "role": "user",
                        "content": "What is our asset allocation policy for high-growth tech?",
                    }]
                },
            },
            timeout=60.0,
        )
        assert resp.status_code == 200, f"FinServe call failed: {resp.text}"
        resp_data = resp.json().get("data", {})
        assert resp_data.get("response")
        assert resp_data.get("tenant_id") == "Bank_Alpha"
    except httpx.ConnectError:
        pytest.skip(f"Gateway not reachable at {GATEWAY_BASE_URL}")
