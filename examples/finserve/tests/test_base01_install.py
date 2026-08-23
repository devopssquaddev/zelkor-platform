import pytest
import subprocess
import json
import httpx

def test_base01_finserve_pods_healthy(kubecontext):
    """
    BASE-01: Verify FinServe demo agent and code executor are deployed and running.
    """
    res = subprocess.run(
        ["kubectl", "--context", kubecontext, "get", "pods", "-o", "json"],
        capture_output=True,
        text=True,
        check=True
    )
    data = json.loads(res.stdout)
    items = data.get("items", [])
    pod_names = [p["metadata"]["name"] for p in items]

    assert any("finserve-agent" in name for name in pod_names), "finserve-agent pod not found"
    assert any("finserve-code-executor" in name for name in pod_names), "finserve-code-executor pod not found"

def test_base01_finserve_runs_stream_api():
    """
    BASE-01 / Path A: Verify FinServe /runs/stream endpoint via Gateway port 8088.
    """
    url = "http://127.0.0.1:8088/runs/stream"
    headers = {
        "Host": "finserve.localhost",
        "Content-Type": "application/json",
        "Authorization": "Bearer dev:Bank_Alpha"
    }
    payload = {
        "assistant_id": "finserve_agent",
        "input": {
            "messages": [{"role": "user", "content": "What is my total portfolio valuation and risk breakdown?"}]
        }
    }
    resp = httpx.post(url, headers=headers, json=payload, timeout=10.0)
    assert resp.status_code == 200, f"Failed /runs/stream call: {resp.text}"
    data = resp.json()
    assert data.get("assistant_id") == "finserve_agent"
    assert data.get("tenant_id") == "Bank_Alpha"
    assert "data" in data
    assert "Bank_Alpha" in data["data"].get("response", "")

def test_base01_langfuse_observability_endpoint():
    """
    BASE-01 / Path A: Verify Langfuse UI / API health endpoint is reachable on port 8088.
    """
    url = "http://127.0.0.1:8088/api/public/health"
    headers = {"Host": "langfuse.localhost"}
    resp = httpx.get(url, headers=headers, timeout=10.0)
    assert resp.status_code == 200, f"Failed Langfuse health check: {resp.text}"
