import os
import pytest
import subprocess
import json
import httpx
import time

GATEWAY_BASE_URL = os.environ.get("GATEWAY_BASE_URL", "http://127.0.0.1:8088")
FINSERVE_HOST_HEADER = os.environ.get("FINSERVE_HOST_HEADER", "finserve.localhost")
LANGFUSE_HOST_HEADER = os.environ.get("LANGFUSE_HOST_HEADER", "langfuse.localhost")


def test_base01_finserve_pods_healthy(kubecontext):
    """E2E smoke: FinServe agent and platform MCP pods are running."""
    try:
        res = subprocess.run(
            ["kubectl", "--context", kubecontext, "get", "pods", "-A", "-o", "json"],
            capture_output=True,
            text=True,
            check=True,
        )
    except Exception as exc:
        pytest.skip(f"Kubernetes cluster not accessible: {exc}")

    pod_names = [p["metadata"]["name"] for p in json.loads(res.stdout).get("items", [])]
    if not any("finserve" in name for name in pod_names):
        pytest.skip(f"FinServe pods not present in context '{kubecontext}'")

    assert any("finserve-agent" in name for name in pod_names)
    assert any("mcp-sandbox" in name for name in pod_names)
    assert any("mcp-gateway" in name for name in pod_names)


def test_base01_finserve_runs_stream_api():
    """E2E smoke: /runs/stream returns 200 with tenant context."""
    url = f"{GATEWAY_BASE_URL}/runs/stream"
    headers = {
        "Host": FINSERVE_HOST_HEADER,
        "Content-Type": "application/json",
        "Authorization": "Bearer dev:Bank_Alpha",
    }
    payload = {
        "assistant_id": "finserve_agent",
        "input": {
            "messages": [{"role": "user", "content": "What is my total portfolio valuation?"}]
        },
    }
    try:
        resp = httpx.post(url, headers=headers, json=payload, timeout=60.0)
        assert resp.status_code == 200, f"Failed /runs/stream call: {resp.text}"
        data = resp.json()
        assert data.get("assistant_id") == "finserve_agent"
        assert data.get("tenant_id") == "Bank_Alpha"
        assert "data" in data
        assert data["data"].get("tenant_id") == "Bank_Alpha"
        assert data["data"].get("response")
    except httpx.ConnectError:
        pytest.skip(f"Gateway not reachable at {GATEWAY_BASE_URL}")


def test_base01_langfuse_observability_endpoint():
    """E2E smoke: Langfuse health endpoint reachable via gateway."""
    url = f"{GATEWAY_BASE_URL}/api/public/health"
    headers = {"Host": LANGFUSE_HOST_HEADER}
    try:
        resp = httpx.get(url, headers=headers, timeout=10.0)
        assert resp.status_code == 200, f"Failed Langfuse health check: {resp.text}"
    except httpx.ConnectError:
        pytest.skip(f"Gateway not reachable at {GATEWAY_BASE_URL}")


def test_base01_finserve_agent_generates_traces():
    """E2E smoke: agent run produces a Langfuse trace for the tenant."""
    url = f"{GATEWAY_BASE_URL}/runs/stream"
    headers = {
        "Host": FINSERVE_HOST_HEADER,
        "Content-Type": "application/json",
        "Authorization": "Bearer dev:Bank_Alpha",
    }
    payload = {
        "assistant_id": "finserve_agent",
        "input": {
            "messages": [{"role": "user", "content": "Summarize my portfolio holdings."}]
        },
    }
    try:
        resp = httpx.post(url, headers=headers, json=payload, timeout=60.0)
        assert resp.status_code == 200, f"FinServe stream call failed: {resp.text}"
    except httpx.ConnectError:
        pytest.skip(f"Gateway not reachable at {GATEWAY_BASE_URL}")

    time.sleep(1.0)
    traces_resp = httpx.get(
        f"{GATEWAY_BASE_URL}/api/public/traces",
        headers={"Host": LANGFUSE_HOST_HEADER},
        auth=(
            os.environ.get("LANGFUSE_PUBLIC_KEY", "pk-lf-zelkor-dev-00000000000000000000"),
            os.environ.get("LANGFUSE_SECRET_KEY", "sk-lf-zelkor-dev-00000000000000000000"),
        ),
        timeout=10.0,
    )
    assert traces_resp.status_code == 200, f"Failed to query Langfuse traces: {traces_resp.text}"
    traces = traces_resp.json().get("data", [])
    matching = [t for t in traces if t.get("userId") == "Bank_Alpha" or "Bank_Alpha" in t.get("tags", [])]
    assert len(matching) > 0, f"Expected Bank_Alpha trace in Langfuse, found: {[t.get('tags') for t in traces]}"
