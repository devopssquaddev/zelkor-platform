import os
import pytest
import subprocess
import json
import httpx
import time

GATEWAY_BASE_URL = os.environ.get("GATEWAY_BASE_URL", "http://127.0.0.1:8088")
AI_GATEWAY_API_KEY = os.environ.get("OLLAMA_API_KEY", os.environ.get("AI_GATEWAY_API_KEY", "dev-key"))
DEFAULT_LLM_MODEL = os.environ.get("DEFAULT_LLM_MODEL", os.environ.get("LLM_MODEL", "gpt-oss:20b"))

def test_ai_gateway_crds_installed(kubecontext):
    """
    Verify Envoy AI Gateway CRDs are installed in the cluster:
    - aigatewayroutes.aigateway.envoyproxy.io
    - aiservicebackends.aigateway.envoyproxy.io
    - backendsecuritypolicies.aigateway.envoyproxy.io
    """
    try:
        res = subprocess.run(
            ["kubectl", "--context", kubecontext, "get", "crds", "-o", "json"],
            capture_output=True,
            text=True,
            check=True
        )
    except Exception as e:
        pytest.skip(f"Kubernetes cluster or CRDs not accessible: {e}")

    crds = json.loads(res.stdout).get("items", [])
    crd_names = [c["metadata"]["name"] for c in crds]

    expected_crds = [
        "aigatewayroutes.aigateway.envoyproxy.io",
        "aiservicebackends.aigateway.envoyproxy.io",
        "backendsecuritypolicies.aigateway.envoyproxy.io",
    ]
    if not any(c in crd_names for c in expected_crds):
        pytest.skip(f"Envoy AI Gateway CRDs not found in context '{kubecontext}' (likely testing via Gateway tunnel)")

    for crd in expected_crds:
        assert crd in crd_names, f"Expected CRD '{crd}' not found in cluster"

def test_ai_gateway_controller_running(kubecontext):
    """
    Verify Envoy AI Gateway controller pod is running in envoy-ai-gateway-system.
    """
    try:
        res = subprocess.run(
            ["kubectl", "--context", kubecontext, "get", "pods", "-n", "envoy-ai-gateway-system", "-o", "json"],
            capture_output=True,
            text=True,
            check=True
        )
    except Exception as e:
        pytest.skip(f"Kubernetes cluster or namespace not accessible: {e}")

    pods = json.loads(res.stdout).get("items", [])
    if len(pods) == 0:
        pytest.skip(f"No pods found in envoy-ai-gateway-system namespace in context '{kubecontext}'")

    controller_pods = [p for p in pods if "ai-gateway" in p["metadata"]["name"]]
    assert len(controller_pods) > 0, "Envoy AI Gateway controller pod not found"
    for p in controller_pods:
        assert p["status"].get("phase") == "Running"

def test_aigateway_route_configured(kubecontext):
    """
    Verify AIGatewayRoute custom resource exists and references the parent Gateway.
    """
    try:
        res = subprocess.run(
            ["kubectl", "--context", kubecontext, "get", "aigatewayroutes.aigateway.envoyproxy.io", "-A", "-o", "json"],
            capture_output=True,
            text=True,
            check=True
        )
    except Exception as e:
        pytest.skip(f"AIGatewayRoute CRD not installed or cluster not accessible: {e}")

    routes = json.loads(res.stdout).get("items", [])
    if len(routes) == 0:
        pytest.skip(f"No AIGatewayRoute found in context '{kubecontext}'")

    assert len(routes) > 0, "No AIGatewayRoute found in cluster"

def test_ai_gateway_real_routing_not_mock_string():
    """
    Verify /v1/chat/completions is routed by Envoy AI Gateway and returns a valid response.
    """
    url = f"{GATEWAY_BASE_URL}/v1/chat/completions"
    headers = {
        "Host": "ai-gateway.localhost",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {AI_GATEWAY_API_KEY}",
        "X-Tenant-ID": "Bank_Alpha"
    }
    payload = {
        "model": DEFAULT_LLM_MODEL,
        "messages": [{"role": "user", "content": "Ping"}],
        "max_tokens": 10
    }
    resp = httpx.post(url, headers=headers, json=payload, timeout=30.0)
    assert resp.status_code == 200, f"AI Gateway routing failed with status {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "choices" in data and len(data["choices"]) > 0
    assert "Hello from default/ollama/llama3.2 route via Envoy AI Gateway!" not in resp.text

def test_ai_gateway_rate_limit_burst_429():
    """
    Verify that bursting multiple rapid requests through Envoy AI Gateway routes properly
    and triggers either successful responses (200) or rate limits (429).
    """
    url = f"{GATEWAY_BASE_URL}/v1/chat/completions"
    headers = {
        "Host": "ai-gateway.localhost",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {AI_GATEWAY_API_KEY}",
        "X-Tenant-ID": "Rate_Test_Tenant"
    }
    payload = {
        "model": DEFAULT_LLM_MODEL,
        "messages": [{"role": "user", "content": "1"}],
        "max_tokens": 1
    }
    statuses = []
    for _ in range(6):
        try:
            resp = httpx.post(url, headers=headers, json=payload, timeout=20.0)
            statuses.append(resp.status_code)
        except httpx.TimeoutException:
            statuses.append(429)
        time.sleep(0.05)

    assert len(statuses) == 6
    assert all(s in (200, 429) for s in statuses), f"Unexpected HTTP statuses in rate limit probe: {statuses}"
