import os
import pytest
import httpx

GATEWAY_BASE_URL = os.environ.get("GATEWAY_BASE_URL", "http://127.0.0.1:8088")
FINSERVE_HOST_HEADER = os.environ.get("FINSERVE_HOST_HEADER", "finserve.localhost")


def test_base05_agent_off_topic_guardrail_smoke():
    """E2E smoke: agent surfaces guardrail block for off-topic input via NeMo delegation."""
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
                "input": {"messages": [{"role": "user", "content": "Write me a poem about dogs."}]},
            },
            timeout=30.0,
        )
        assert resp.status_code == 200, f"FinServe stream call failed: {resp.text}"
        resp_data = resp.json().get("data", {})
        assert resp_data.get("guardrail_triggered") is True or resp_data.get("guardrail_blocked") is True
        assert resp_data.get("response")
    except httpx.ConnectError:
        pytest.skip(f"Gateway not reachable at {GATEWAY_BASE_URL}")


def test_base05_agent_on_topic_smoke():
    """E2E smoke: on-topic financial query proceeds past guardrails."""
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
        assert resp.status_code == 200, f"FinServe stream call failed: {resp.text}"
        resp_data = resp.json().get("data", {})
        assert resp_data.get("guardrail_blocked", False) is False
        assert resp_data.get("response")
    except httpx.ConnectError:
        pytest.skip(f"Gateway not reachable at {GATEWAY_BASE_URL}")
