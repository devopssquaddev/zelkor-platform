import pytest
import httpx
import uuid
import datetime
import time

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

def test_langfuse_traces_gvisor_outbreak_prevention():
    """
    Verify that an adversarial code outbreak attempt is executed inside gVisor sandbox,
    prevented safely, and traced in Langfuse with 'gvisor-sandbox' and 'outbreak-prevention-verified' tags.
    """
    url = f"{GATEWAY_BASE_URL}/runs/stream"
    headers = {
        "Host": FINSERVE_HOST_HEADER,
        "Content-Type": "application/json",
        "Authorization": "Bearer dev:Bank_Alpha"
    }
    adversarial_code = """import os, stat
results = {}
try:
    os.mknod('/tmp/fake_sda_langfuse', stat.S_IFBLK | 0o660, os.makedev(8, 1))
    with open('/tmp/fake_sda_langfuse', 'rb') as f:
        f.read(10)
    results['mknod_escape'] = 'EXPLOIT_SUCCEEDED'
except Exception as e:
    results['mknod_escape'] = f'BLOCKED: {type(e).__name__}'

print(results)
"""
    payload = {
        "assistant_id": "finserve_agent",
        "input": {
            "messages": [{"role": "user", "content": f"Execute this Python code:\n```python\n{adversarial_code}\n```"}]
        }
    }
    resp = httpx.post(url, headers=headers, json=payload, timeout=10.0)
    assert resp.status_code == 200, f"FinServe outbreak execution call failed: {resp.text}"
    data = resp.json()
    assert data.get("tenant_id") == "Bank_Alpha"
    stdout = data.get("data", {}).get("execution_result", {}).get("stdout", "")
    assert "BLOCKED" in stdout
    assert "EXPLOIT_SUCCEEDED" not in stdout

    # Query Langfuse API to verify trace with outbreak-prevention-verified tag exists
    time.sleep(1.0)
    langfuse_url = f"{GATEWAY_BASE_URL}/api/public/traces"
    langfuse_headers = {"Host": LANGFUSE_HOST_HEADER}
    traces_resp = httpx.get(
        langfuse_url,
        headers=langfuse_headers,
        auth=(DEV_PUBLIC_KEY, DEV_SECRET_KEY),
        timeout=10.0
    )
    assert traces_resp.status_code == 200, f"Langfuse traces fetch failed: {traces_resp.text}"
    traces_data = traces_resp.json().get("data", [])
    
    # Check that a trace exists containing gvisor or outbreak tags
    outbreak_traces = [
        t for t in traces_data
        if any(tag in ["gvisor-sandbox", "outbreak-prevention-verified"] for tag in t.get("tags", []))
    ]
    assert len(outbreak_traces) > 0, f"Expected outbreak prevention trace in Langfuse, found tags: {[t.get('tags') for t in traces_data]}"
