import os
import pytest
import subprocess
import json
import httpx
import time

from tests.helpers.llm import llm_model_or_skip

GATEWAY_BASE_URL = os.environ.get("GATEWAY_BASE_URL", "http://127.0.0.1:8088")
AI_GATEWAY_API_KEY = os.environ.get("AI_GATEWAY_API_KEY", os.environ.get("ZELKOR_CONSUMER_KEY", "dev-key"))

def test_gateway_controller_running(kubecontext):
    """
    Verify Envoy Gateway controller is running in the envoy-gateway-system namespace.
    """
    try:
        res = subprocess.run(
            ["kubectl", "--context", kubecontext, "get", "pods", "-n", "envoy-gateway-system", "-o", "json"],
            capture_output=True,
            text=True,
            check=True
        )
    except Exception as e:
        pytest.skip(f"Kubernetes cluster or namespace not accessible: {e}")

    data = json.loads(res.stdout)
    items = data.get("items", [])
    if len(items) == 0:
        pytest.skip(f"No envoy-gateway-system pods found in context '{kubecontext}' (likely testing via Gateway tunnel)")

    controller_pods = [p for p in items if "envoy-gateway" in p["metadata"]["name"]]
    assert len(controller_pods) > 0, "Envoy Gateway controller pod not found"

    for pod in controller_pods:
        phase = pod["status"].get("phase")
        assert phase == "Running", f"Envoy Gateway controller pod not in Running phase: {phase}"

def test_gateway_resources_configured(kubecontext):
    """
    Verify GatewayClass, Gateway, and HTTPRoute / AIGatewayRoute resources exist for platform components.
    """
    try:
        # 1. Verify GatewayClass
        gc_res = subprocess.run(
            ["kubectl", "--context", kubecontext, "get", "gatewayclass", "-o", "json"],
            capture_output=True,
            text=True,
            check=True
        )
    except Exception as e:
        pytest.skip(f"GatewayClass CRD not installed or cluster not accessible: {e}")

    gc_data = json.loads(gc_res.stdout)
    gc_names = [item["metadata"]["name"] for item in gc_data.get("items", [])]
    assert "eg" in gc_names, f"GatewayClass 'eg' not found in {gc_names}"

    # 2. Verify Gateway
    gw_res = subprocess.run(
        ["kubectl", "--context", kubecontext, "get", "gateway", "-A", "-o", "json"],
        capture_output=True,
        text=True,
        check=True
    )
    gw_data = json.loads(gw_res.stdout)
    gw_names = [item["metadata"]["name"] for item in gw_data.get("items", [])]
    assert any("zelkor-platform" in name for name in gw_names), f"zelkor-platform gateway not found in {gw_names}"

    # 3. Verify HTTPRoutes & AIGatewayRoutes
    hr_res = subprocess.run(
        ["kubectl", "--context", kubecontext, "get", "httproute", "-A", "-o", "json"],
        capture_output=True,
        text=True,
        check=True
    )
    hr_data = json.loads(hr_res.stdout)
    items = hr_data.get("items", [])
    route_names = [i["metadata"]["name"] for i in items]
    assert any("zelkor-platform" in name for name in route_names), f"zelkor-platform httproute not found in {route_names}"

    all_hosts = []
    for route in items:
        for rule in route.get("spec", {}).get("rules", []):
            for host in rule.get("hostnames", []):
                all_hosts.append(host)
        for host in route.get("spec", {}).get("hostnames", []):
            all_hosts.append(host)

    # Also check AIGatewayRoutes
    aieg_res = subprocess.run(
        ["kubectl", "--context", kubecontext, "get", "aigatewayroutes.aigateway.envoyproxy.io", "-A", "-o", "json"],
        capture_output=True,
        text=True
    )
    if aieg_res.returncode == 0:
        aieg_data = json.loads(aieg_res.stdout)
        for route in aieg_data.get("items", []):
            for host in route.get("spec", {}).get("hostnames", []):
                all_hosts.append(host)

    assert "langfuse.localhost" in all_hosts, f"langfuse.localhost not in {all_hosts}"
    assert "ai-gateway.localhost" in all_hosts, f"ai-gateway.localhost not in {all_hosts}"
    assert "aegra.localhost" in all_hosts, f"aegra.localhost not in {all_hosts}"

def test_gateway_routing_http_endpoints():
    """
    Verify platform HTTP routing through Gateway via Host headers.
    """
    endpoints = [
        ("langfuse.localhost", "/api/public/health"),
        ("aegra.localhost", "/health"),
    ]

    for host, path in endpoints:
        url = f"{GATEWAY_BASE_URL}{path}"
        headers = {"Host": host}
        
        success = False
        last_error = None
        for _ in range(15):
            try:
                resp = httpx.get(url, headers=headers, timeout=5.0)
                if resp.status_code == 200:
                    success = True
                    break
            except Exception as e:
                last_error = e
            time.sleep(1)

        assert success, f"Failed to reach {host}{path} via Gateway at {GATEWAY_BASE_URL}: {last_error}"

def test_gateway_multi_provider_routing_via_gateway():
    """
    Verify OpenAI SDK-compatible routing via Envoy AI Gateway.
    """
    model = llm_model_or_skip()
    url = f"{GATEWAY_BASE_URL}/v1/chat/completions"
    headers = {
        "Host": "ai-gateway.localhost",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {AI_GATEWAY_API_KEY}",
        "X-Tenant-ID": "Squad_Alpha"
    }

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": f"Test prompt for {model}"}],
        "max_tokens": 10
    }
    resp = httpx.post(url, headers=headers, json=payload, timeout=30.0)
    assert resp.status_code == 200, f"AI Gateway call failed with status {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "choices" in data, f"No choices in response: {data}"
    assert len(data["choices"]) > 0
