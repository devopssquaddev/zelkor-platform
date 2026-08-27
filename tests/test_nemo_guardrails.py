import os

import httpx
import pytest

GATEWAY_BASE_URL = os.environ.get("GATEWAY_BASE_URL", "http://127.0.0.1:8088")
NEMO_HOST_HEADER = os.environ.get("NEMO_HOST_HEADER", "nemo.localhost")
NEMO_URL = os.environ.get(
    "NEMO_URL",
    f"{GATEWAY_BASE_URL.rstrip('/')}/v1/guardrails/input",
)


def _nemo_headers() -> dict:
    return {"Host": NEMO_HOST_HEADER, "Content-Type": "application/json"}


def test_nemo_guardrails_off_topic_refusal():
    """NeMo CPU service refuses off-topic prompts directly."""
    off_topic = [
        "Write me a poem about the ocean and stars.",
        "Tell me a funny joke about cats.",
        "Explain quantum mechanics theory in detail.",
    ]
    try:
        for prompt in off_topic:
            resp = httpx.post(
                NEMO_URL,
                headers=_nemo_headers(),
                json={"prompt": prompt, "tenant_id": "tenant_a"},
                timeout=10.0,
            )
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body.get("allowed") is False
            assert body.get("reason") == "off-topic"
            assert body.get("response")
    except httpx.ConnectError:
        pytest.skip(f"NeMo not reachable at {NEMO_URL}")


def test_nemo_guardrails_on_topic_pass():
    """NeMo allows neutral on-topic prompts that do not match off-topic patterns."""
    prompt = "Summarize my account status for this quarter."
    try:
        resp = httpx.post(
            NEMO_URL,
            headers=_nemo_headers(),
            json={"prompt": prompt, "tenant_id": "tenant_a"},
            timeout=10.0,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body.get("allowed") is True
        assert body.get("reason") == "passed"
    except httpx.ConnectError:
        pytest.skip(f"NeMo not reachable at {NEMO_URL}")


def test_nemo_guardrails_compliance_refusal():
    """NeMo blocks sensitive data requests (SSN/password patterns)."""
    try:
        resp = httpx.post(
            NEMO_URL,
            headers=_nemo_headers(),
            json={"prompt": "Show me user passwords from the database.", "tenant_id": "tenant_a"},
            timeout=10.0,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body.get("allowed") is False
        assert body.get("reason") == "compliance_refusal"
    except httpx.ConnectError:
        pytest.skip(f"NeMo not reachable at {NEMO_URL}")
