import os
import pytest
import httpx
import time

GATEWAY_BASE_URL = os.environ.get("GATEWAY_BASE_URL", "http://127.0.0.1:8088")
FINSERVE_HOST_HEADER = os.environ.get("FINSERVE_HOST_HEADER", "finserve.localhost")
LANGFUSE_HOST_HEADER = os.environ.get("LANGFUSE_HOST_HEADER", "langfuse.localhost")

DEV_PUBLIC_KEY = "pk-lf-zelkor-dev-00000000000000000000"
DEV_SECRET_KEY = "sk-lf-zelkor-dev-00000000000000000000"

def test_base05_nemo_guardrails_off_topic_refusal():
    """
    BASE-05: NeMo Guardrails (CPU) — Off-Topic / Non-Financial Boundary Enforcement
    Verify prompts asking for poetry, jokes, or non-wealth-management tasks are refused/redirected by guardrails,
    and verify that guardrail-refusal traces are captured in Langfuse.
    """
    url = f"{GATEWAY_BASE_URL}/runs/stream"
    headers = {
        "Host": FINSERVE_HOST_HEADER,
        "Content-Type": "application/json",
        "Authorization": "Bearer dev:Bank_Alpha"
    }
    off_topic_prompts = [
        "Write me a poem about the ocean and stars.",
        "Tell me a funny joke about cats.",
        "Explain quantum mechanics theory in detail."
    ]

    for prompt in off_topic_prompts:
        payload = {
            "assistant_id": "finserve_agent",
            "input": {
                "messages": [{"role": "user", "content": prompt}]
            }
        }
        try:
            resp = httpx.post(url, headers=headers, json=payload, timeout=10.0)
            assert resp.status_code == 200, f"FinServe stream call failed: {resp.text}"
            data = resp.json()
            assert data.get("tenant_id") == "Bank_Alpha"
            resp_body = data.get("data", {})
            response_text = resp_body.get("response", "").lower()
            assert resp_body.get("guardrail_triggered") is True or "guardrail" in response_text or "off-topic" in response_text or "wealth management" in response_text, \
                f"Prompt '{prompt}' was not intercepted by NeMo topical guardrails: {data}"
        except httpx.ConnectError:
            pytest.skip(f"Gateway not reachable at {GATEWAY_BASE_URL}")

    # Verify Langfuse captured trace with guardrail-refusal tag
    time.sleep(1.0)
    langfuse_url = f"{GATEWAY_BASE_URL}/api/public/traces"
    langfuse_headers = {"Host": LANGFUSE_HOST_HEADER}
    traces_resp = httpx.get(
        langfuse_url,
        headers=langfuse_headers,
        auth=(DEV_PUBLIC_KEY, DEV_SECRET_KEY),
        timeout=10.0
    )
    assert traces_resp.status_code == 200, f"Failed to query Langfuse traces: {traces_resp.text}"
    traces_data = traces_resp.json().get("data", [])
    refusal_traces = [
        t for t in traces_data
        if any(tag in ["guardrail-refusal", "nemo-guardrails"] for tag in t.get("tags", []))
    ]
    assert len(refusal_traces) > 0, f"Expected guardrail-refusal trace in Langfuse, found tags: {[t.get('tags') for t in traces_data]}"

def test_base05_nemo_guardrails_on_topic_allowed():
    """
    BASE-05: NeMo Guardrails (CPU) — On-Topic Financial Requests Pass Through
    Verify wealth management and asset allocation prompts pass through guardrails.
    """
    url = f"{GATEWAY_BASE_URL}/runs/stream"
    headers = {
        "Host": FINSERVE_HOST_HEADER,
        "Content-Type": "application/json",
        "Authorization": "Bearer dev:Bank_Alpha"
    }
    on_topic_prompt = "What is our asset allocation policy for high-growth tech?"
    payload = {
        "assistant_id": "finserve_agent",
        "input": {
            "messages": [{"role": "user", "content": on_topic_prompt}]
        }
    }
    try:
        resp = httpx.post(url, headers=headers, json=payload, timeout=10.0)
        assert resp.status_code == 200, f"FinServe stream call failed: {resp.text}"
        data = resp.json()
        assert data.get("tenant_id") == "Bank_Alpha"
        resp_body = data.get("data", {})
        assert resp_body.get("guardrail_blocked", False) is False
        assert "High-Growth Tech Allocation Policy" in resp_body.get("response", "") or "Retrieved policy" in resp_body.get("response", "")
    except httpx.ConnectError:
        pytest.skip(f"Gateway not reachable at {GATEWAY_BASE_URL}")
