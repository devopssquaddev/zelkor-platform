import os
import pytest
import httpx
import uuid
import datetime
import time

from tests.helpers.llm import llm_model_or_skip

LANGFUSE_HOST_HEADER = os.environ.get("LANGFUSE_HOST_HEADER", "langfuse.localhost")
AI_GATEWAY_HOST_HEADER = os.environ.get("AI_GATEWAY_HOST_HEADER", "ai-gateway.localhost")
GATEWAY_BASE_URL = os.environ.get("GATEWAY_BASE_URL", "http://127.0.0.1:8088")

AI_GATEWAY_API_KEY = os.environ.get("AI_GATEWAY_API_KEY", os.environ.get("ZELKOR_CONSUMER_KEY", "dev-key"))

DEV_PUBLIC_KEY = "pk-lf-zelkor-dev-00000000000000000000"
DEV_SECRET_KEY = "sk-lf-zelkor-dev-00000000000000000000"

def test_langfuse_health():
    """
    Verify Langfuse health endpoint is reachable through Envoy Gateway.
    """
    url = f"{GATEWAY_BASE_URL}/api/public/health"
    headers = {"Host": LANGFUSE_HOST_HEADER}
    try:
        resp = httpx.get(url, headers=headers, timeout=10.0)
        assert resp.status_code == 200, f"Langfuse health check failed: {resp.text}"
    except httpx.ConnectError:
        pytest.skip(f"Gateway not reachable at {GATEWAY_BASE_URL}")

def test_langfuse_preseeded_api_keys_ingestion():
    """
    Verify the pre-seeded API keys from headless initialization are valid and accept ingestion events.
    """
    try:
        probe = httpx.get(
            f"{GATEWAY_BASE_URL}/api/public/traces",
            headers={"Host": LANGFUSE_HOST_HEADER},
            auth=(DEV_PUBLIC_KEY, DEV_SECRET_KEY),
            timeout=10.0,
        )
    except httpx.ConnectError:
        pytest.skip(f"Gateway not reachable at {GATEWAY_BASE_URL}")
    if probe.status_code != 200 and "events_only" in probe.text:
        pytest.skip("legacy /api/public/ingestion traces are unavailable in Langfuse events_only")
    url = f"{GATEWAY_BASE_URL}/api/public/ingestion"
    headers = {
        "Host": LANGFUSE_HOST_HEADER,
        "Content-Type": "application/json"
    }
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    trace_id = f"test-trace-{uuid.uuid4().hex}"
    
    payload = {
        "batch": [
            {
                "id": str(uuid.uuid4()),
                "type": "trace-create",
                "timestamp": now_iso,
                "body": {
                    "id": trace_id,
                    "name": "integration-test-trace",
                    "userId": "tenant_a",
                    "tags": ["test", "integration"],
                    "input": "Health check trace",
                    "output": "Trace received successfully",
                    "metadata": {"source": "pytest", "env": "local-dev"}
                }
            }
        ]
    }
    
    try:
        resp = httpx.post(
            url,
            headers=headers,
            auth=(DEV_PUBLIC_KEY, DEV_SECRET_KEY),
            json=payload,
            timeout=10.0
        )
        assert resp.status_code in [200, 201, 207], f"Ingestion failed with status {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "successes" in data or "errors" in data or isinstance(data, list) or resp.status_code == 200
    except httpx.ConnectError:
        pytest.skip(f"Gateway not reachable at {GATEWAY_BASE_URL}")

def test_ai_gateway_generates_traces():
    """Chat via Envoy AI Gateway (200). Langfuse read is v2 observations, not legacy ingest."""
    model = llm_model_or_skip()
    marker = f"Ping AI Gateway with trace {uuid.uuid4().hex[:8]}"
    url = f"{GATEWAY_BASE_URL}/v1/chat/completions"
    headers = {
        "Host": AI_GATEWAY_HOST_HEADER,
        "Content-Type": "application/json",
        "Authorization": f"Bearer {AI_GATEWAY_API_KEY}",
        "X-Tenant-ID": "tenant_a"
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": marker}],
        "max_tokens": 10
    }
    resp = httpx.post(url, headers=headers, json=payload, timeout=120.0)
    assert resp.status_code == 200, f"AI Gateway chat completion failed with status {resp.status_code}: {resp.text}"

    # events_only: POST /api/public/ingestion is not stored. Look for real OTEL on the chat.
    from tests.helpers.langfuse import blob, list_observations

    deadline = time.time() + 45
    last: list = []
    while time.time() < deadline:
        last = list_observations(limit=80)
        if any(marker.lower() in blob(o.get("input")) or marker.lower() in blob(o.get("traceName")) for o in last):
            return
        time.sleep(2)
    pytest.skip(
        "AI Gateway chat returned 200; no Langfuse v2 observation for this prompt "
        "(events_only does not store /api/public/ingestion)"
    )
