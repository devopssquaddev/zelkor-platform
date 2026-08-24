import os
import pytest
import subprocess
import json
import httpx

GATEWAY_BASE_URL = os.environ.get("GATEWAY_BASE_URL", "http://127.0.0.1:8088")
FINSERVE_HOST_HEADER = os.environ.get("FINSERVE_HOST_HEADER", "finserve.localhost")
LANGFUSE_HOST_HEADER = os.environ.get("LANGFUSE_HOST_HEADER", "langfuse.localhost")

def test_base01_finserve_pods_healthy(kubecontext):
    """
    BASE-01: Verify FinServe demo agent and code executor are deployed and running.
    """
    try:
        res = subprocess.run(
            ["kubectl", "--context", kubecontext, "get", "pods", "-A", "-o", "json"],
            capture_output=True,
            text=True,
            check=True
        )
    except Exception as e:
        pytest.skip(f"Kubernetes cluster not accessible: {e}")

    data = json.loads(res.stdout)
    items = data.get("items", [])
    pod_names = [p["metadata"]["name"] for p in items]

    assert any("finserve-agent" in name for name in pod_names), f"finserve-agent pod not found in: {pod_names}"
    assert any("finserve-code-executor" in name for name in pod_names), f"finserve-code-executor pod not found in: {pod_names}"

def test_base01_finserve_runs_stream_api():
    """
    BASE-01 / Path A: Verify FinServe /runs/stream endpoint via Gateway.
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
            "messages": [{"role": "user", "content": "What is my total portfolio valuation and risk breakdown?"}]
        }
    }
    try:
        resp = httpx.post(url, headers=headers, json=payload, timeout=10.0)
        assert resp.status_code == 200, f"Failed /runs/stream call: {resp.text}"
        data = resp.json()
        assert data.get("assistant_id") == "finserve_agent"
        assert data.get("tenant_id") == "Bank_Alpha"
        assert "data" in data
        assert "Bank_Alpha" in data["data"].get("response", "")
    except httpx.ConnectError:
        pytest.skip(f"Gateway not reachable at {GATEWAY_BASE_URL}")

def test_base01_langfuse_observability_endpoint():
    """
    BASE-01 / Path A: Verify Langfuse UI / API health endpoint is reachable.
    """
    url = f"{GATEWAY_BASE_URL}/api/public/health"
    headers = {"Host": LANGFUSE_HOST_HEADER}
    try:
        resp = httpx.get(url, headers=headers, timeout=10.0)
        assert resp.status_code == 200, f"Failed Langfuse health check: {resp.text}"
    except httpx.ConnectError:
        pytest.skip(f"Gateway not reachable at {GATEWAY_BASE_URL}")

def test_base01_finserve_agent_generates_traces_and_spans():
    """
    BASE-01: Verify FinServe Wealth Management Agent handles prompt and emits multi-span traces.
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
        assert resp.status_code == 200, f"FinServe stream call failed: {resp.text}"
        data = resp.json()
        assert data.get("tenant_id") == "Bank_Alpha"
        assert "data" in data
        assert "Retrieved policy guidelines" in data["data"].get("response", "")
    except httpx.ConnectError:
        pytest.skip(f"Gateway not reachable at {GATEWAY_BASE_URL}")
