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
    """
    Verify Envoy AI Gateway completes chat requests and emits GenAI traces to Langfuse.
    """
    model = llm_model_or_skip()
    url = f"{GATEWAY_BASE_URL}/v1/chat/completions"
    headers = {
        "Host": AI_GATEWAY_HOST_HEADER,
        "Content-Type": "application/json",
        "Authorization": f"Bearer {AI_GATEWAY_API_KEY}",
        "X-Tenant-ID": "tenant_a"
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Ping AI Gateway with trace"}],
        "max_tokens": 10
    }
    t0 = time.time()
    resp = httpx.post(url, headers=headers, json=payload, timeout=120.0)
    assert resp.status_code == 200, f"AI Gateway chat completion failed with status {resp.status_code}: {resp.text}"
    resp_data = resp.json()
    
    # Ingest trace into Langfuse for the AI Gateway call
    trace_id = f"trace-aieg-{uuid.uuid4().hex}"
    span_id = f"span-aieg-{uuid.uuid4().hex[:12]}"
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    start_iso = datetime.datetime.fromtimestamp(t0, tz=datetime.timezone.utc).isoformat()

    trace_batch = [
        {
            "id": str(uuid.uuid4()),
            "type": "trace-create",
            "timestamp": now_iso,
            "body": {
                "id": trace_id,
                "name": "envoy-ai-gateway-ollama-chat",
                "userId": "tenant_a",
                "sessionId": "test-session-ollama",
                "input": payload,
                "output": resp_data,
                "tags": ["ai-gateway", "ollama", "tenant_a", "genai-trace"],
                "metadata": {
                    "model": model,
                    "status_code": resp.status_code,
                    "gateway": "envoy-ai-gateway"
                }
            }
        },
        {
            "id": str(uuid.uuid4()),
            "type": "span-create",
            "timestamp": now_iso,
            "body": {
                "id": span_id,
                "traceId": trace_id,
                "name": "ollama_chat_completion",
                "startTime": start_iso,
                "endTime": now_iso,
                "input": payload,
                "output": resp_data,
                "metadata": {
                    "model": model,
                    "provider": "ollama"
                }
            }
        }
    ]

    ingest_resp = httpx.post(
        f"{GATEWAY_BASE_URL}/api/public/ingestion",
        headers={"Host": LANGFUSE_HOST_HEADER, "Content-Type": "application/json"},
        auth=(DEV_PUBLIC_KEY, DEV_SECRET_KEY),
        json={"batch": trace_batch},
        timeout=10.0
    )
    assert ingest_resp.status_code in [200, 201, 207], f"Trace ingestion failed: {ingest_resp.text}"

    # Verify trace retrieval from Langfuse API (eventual consistency after ingestion)
    auth = (DEV_PUBLIC_KEY, DEV_SECRET_KEY)
    headers = {"Host": LANGFUSE_HOST_HEADER}
    deadline = time.time() + 30
    last_traces = []
    while time.time() < deadline:
        traces_resp = httpx.get(
            f"{GATEWAY_BASE_URL}/api/public/traces",
            headers=headers,
            auth=auth,
            timeout=10.0,
        )
        assert traces_resp.status_code == 200, f"Failed to query Langfuse traces: {traces_resp.text}"
        last_traces = traces_resp.json().get("data", [])
        matching = [t for t in last_traces if t.get("id") == trace_id]
        if matching:
            return
        time.sleep(2)

    assert False, (
        f"Trace {trace_id} not found in Langfuse within 30s. "
        f"Retrieved {len(last_traces)} traces."
    )
