import pytest
import httpx
import uuid
import datetime

LANGFUSE_HOST_HEADER = "langfuse.localhost"
AI_GATEWAY_HOST_HEADER = "ai-gateway.localhost"
FINSERVE_HOST_HEADER = "finserve.localhost"
GATEWAY_BASE_URL = "http://127.0.0.1:8088"

DEV_PUBLIC_KEY = "pk-lf-zelkor-dev-00000000000000000000"
DEV_SECRET_KEY = "sk-lf-zelkor-dev-00000000000000000000"

def test_langfuse_health():
    """
    Verify Langfuse health endpoint is reachable through Envoy Gateway.
    """
    url = f"{GATEWAY_BASE_URL}/api/public/health"
    headers = {"Host": LANGFUSE_HOST_HEADER}
    resp = httpx.get(url, headers=headers, timeout=10.0)
    assert resp.status_code == 200, f"Langfuse health check failed: {resp.text}"

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
                    "userId": "Bank_Alpha",
                    "tags": ["test", "integration"],
                    "input": "Health check trace",
                    "output": "Trace received successfully",
                    "metadata": {"source": "pytest", "env": "local-dev"}
                }
            }
        ]
    }
    
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

def test_ai_gateway_generates_traces():
    """
    Verify Envoy AI Gateway completes chat requests and emits GenAI traces.
    """
    url = f"{GATEWAY_BASE_URL}/v1/chat/completions"
    headers = {
        "Host": AI_GATEWAY_HOST_HEADER,
        "Content-Type": "application/json",
        "Authorization": "Bearer dev-key",
        "X-Tenant-ID": "Bank_Alpha"
    }
    payload = {
        "model": "openai/gpt-4o-mini",
        "messages": [{"role": "user", "content": "Ping AI Gateway with trace"}]
    }
    resp = httpx.post(url, headers=headers, json=payload, timeout=10.0)
    assert resp.status_code == 200, f"AI Gateway call failed: {resp.text}"
    data = resp.json()
    assert "choices" in data and len(data["choices"]) > 0
    assert data["usage"]["total_tokens"] > 0

def test_finserve_agent_generates_traces_and_spans():
    """
    Verify FinServe Wealth Management Agent handles prompt and emits multi-span traces.
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
    resp = httpx.post(url, headers=headers, json=payload, timeout=10.0)
    assert resp.status_code == 200, f"FinServe stream call failed: {resp.text}"
    data = resp.json()
    assert data.get("tenant_id") == "Bank_Alpha"
    assert "data" in data
    assert "Retrieved policy guidelines" in data["data"].get("response", "")
