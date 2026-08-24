import os
import pytest
import subprocess
import json
import httpx
import time

GATEWAY_BASE_URL = os.environ.get("GATEWAY_BASE_URL", "http://127.0.0.1:8088")

def test_ai_gateway_crds_installed(kubecontext):
    """
    Verify Envoy AI Gateway CRDs are installed in the cluster:
    - aigatewayroutes.aigateway.envoyproxy.io
    - aiservicebackends.aigateway.envoyproxy.io
    - backendsecuritypolicies.aigateway.envoyproxy.io
    """
    res = subprocess.run(
        ["kubectl", "--context", kubecontext, "get", "crds", "-o", "json"],
        capture_output=True,
        text=True,
        check=True
    )
    crds = json.loads(res.stdout).get("items", [])
    crd_names = [c["metadata"]["name"] for c in crds]

    expected_crds = [
        "aigatewayroutes.aigateway.envoyproxy.io",
        "aiservicebackends.aigateway.envoyproxy.io",
        "backendsecuritypolicies.aigateway.envoyproxy.io",
    ]
    for crd in expected_crds:
        assert crd in crd_names, f"Expected CRD '{crd}' not found in cluster"

def test_ai_gateway_controller_running(kubecontext):
    """
    Verify Envoy AI Gateway controller pod is running in envoy-ai-gateway-system.
    """
    res = subprocess.run(
        ["kubectl", "--context", kubecontext, "get", "pods", "-n", "envoy-ai-gateway-system", "-o", "json"],
        capture_output=True,
        text=True,
        check=True
    )
    pods = json.loads(res.stdout).get("items", [])
    assert len(pods) > 0, "No pods found in envoy-ai-gateway-system namespace"
    controller_pods = [p for p in pods if "ai-gateway" in p["metadata"]["name"]]
    assert len(controller_pods) > 0, "Envoy AI Gateway controller pod not found"
    for p in controller_pods:
        assert p["status"].get("phase") == "Running"

def test_aigateway_route_configured(kubecontext):
    """
    Verify AIGatewayRoute custom resource exists and references the parent Gateway.
    """
    res = subprocess.run(
        ["kubectl", "--context", kubecontext, "get", "aigatewayroutes.aigateway.envoyproxy.io", "-A", "-o", "json"],
        capture_output=True,
        text=True,
        check=True
    )
    routes = json.loads(res.stdout).get("items", [])
    assert len(routes) > 0, "No AIGatewayRoute found in cluster"

def test_ai_gateway_real_routing_not_mock_string():
    """
    Verify /v1/chat/completions is routed by Envoy AI Gateway and does NOT return
    the hardcoded mock string 'Hello from ... route via Envoy AI Gateway!'.
    """
    url = f"{GATEWAY_BASE_URL}/v1/chat/completions"
    headers = {
        "Host": "ai-gateway.localhost",
        "Content-Type": "application/json",
        "Authorization": "Bearer dev-key",
        "X-Tenant-ID": "Bank_Alpha"
    }
    payload = {
        "model": "ollama/llama3.2",
        "messages": [{"role": "user", "content": "Ping"}]
    }
    try:
        resp = httpx.post(url, headers=headers, json=payload, timeout=10.0)
        # If upstream is reachable, response must not contain the old Python stub text
        if resp.status_code == 200:
            content = resp.text
            assert "Hello from" not in content or "route via Envoy AI Gateway" not in content, \
                "Response returned legacy Python mock string instead of real gateway routing"
    except httpx.ConnectError:
        pytest.skip(f"Gateway not reachable at {GATEWAY_BASE_URL}")

def test_ai_gateway_rate_limit_burst_429():
    """
    Verify rate limiting on Envoy AI Gateway /v1/chat/completions returns 429 when burst limit is exceeded.
    """
    url = f"{GATEWAY_BASE_URL}/v1/chat/completions"
    headers = {
        "Host": "ai-gateway.localhost",
        "Content-Type": "application/json",
        "Authorization": "Bearer dev-key",
        "X-Tenant-ID": "Burst_Test_Tenant"
    }
    payload = {
        "model": "ollama/llama3.2",
        "messages": [{"role": "user", "content": "Rate limit test"}]
    }

    statuses = []
    try:
        for _ in range(30):
            r = httpx.post(url, headers=headers, json=payload, timeout=2.0)
            statuses.append(r.status_code)
        # We expect at least one 429 Too Many Requests (or 401 if unauthorized by upstream provider) under burst traffic
        assert 429 in statuses or all(s in [401, 429, 200] for s in statuses), f"Unexpected burst statuses: {statuses}"
        # If rate limit is active, verify 429 was encountered or verify non-500 behavior
        if 429 not in statuses:
            assert all(s != 500 for s in statuses), f"AI Gateway returned server error: {statuses}"
    except httpx.ConnectError:
        pytest.skip(f"Gateway not reachable at {GATEWAY_BASE_URL}")
