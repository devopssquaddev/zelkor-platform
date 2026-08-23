import pytest
import subprocess
import json
import httpx
import time

def test_gateway_controller_running(kubecontext):
    """
    Verify Envoy Gateway controller is running in the envoy-gateway-system namespace.
    """
    res = subprocess.run(
        ["kubectl", "--context", kubecontext, "get", "pods", "-n", "envoy-gateway-system", "-o", "json"],
        capture_output=True,
        text=True,
        check=True
    )
    data = json.loads(res.stdout)
    items = data.get("items", [])
    assert len(items) > 0, "No envoy-gateway-system pods found"

    controller_pods = [p for p in items if "envoy-gateway" in p["metadata"]["name"]]
    assert len(controller_pods) > 0, "Envoy Gateway controller pod not found"

    for pod in controller_pods:
        phase = pod["status"].get("phase")
        assert phase == "Running", f"Envoy Gateway controller pod not in Running phase: {phase}"

def test_gateway_resources_configured(kubecontext):
    """
    Verify GatewayClass, Gateway, and HTTPRoute resources exist with expected host rules.
    """
    # 1. Verify GatewayClass
    gc_res = subprocess.run(
        ["kubectl", "--context", kubecontext, "get", "gatewayclass", "-o", "json"],
        capture_output=True,
        text=True,
        check=True
    )
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

    # 3. Verify HTTPRoutes
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
        # Also check top-level hostnames if set
        for host in route.get("spec", {}).get("hostnames", []):
            all_hosts.append(host)

    assert "langfuse.localhost" in all_hosts, f"langfuse.localhost not in {all_hosts}"
    assert "ai-gateway.localhost" in all_hosts, f"ai-gateway.localhost not in {all_hosts}"
    assert "aegra.localhost" in all_hosts, f"aegra.localhost not in {all_hosts}"

def test_gateway_routing_http_endpoints():
    """
    Verify HTTP routing through localhost:8088 via Host headers to Envoy Gateway.
    """
    endpoints = [
        ("langfuse.localhost", "/api/public/health"),
        ("ai-gateway.localhost", "/ready"),
        ("aegra.localhost", "/health"),
        ("finserve.localhost", "/health"),
    ]

    for host, path in endpoints:
        url = f"http://127.0.0.1:8088{path}"
        headers = {"Host": host}
        
        # Retry briefly for Gateway sync
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

        assert success, f"Failed to reach {host}{path} via Envoy Gateway on port 8088: {last_error}"

def test_gateway_multi_provider_routing_via_gateway():
    """
    Verify Path A OpenAI SDK-compatible routing across multiple LLM providers:
    - openai/gpt-4o-mini
    - anthropic/claude-3-5-sonnet
    - gemini/gemini-1.5-flash
    - ollama/llama3.2
    - vllm/llama3.2
    """
    providers = [
        "openai/gpt-4o-mini",
        "anthropic/claude-3-5-sonnet",
        "gemini/gemini-1.5-flash",
        "ollama/llama3.2",
        "vllm/llama3.2",
    ]

    url = "http://127.0.0.1:8088/v1/chat/completions"
    headers = {
        "Host": "ai-gateway.localhost",
        "Content-Type": "application/json",
        "Authorization": "Bearer dev-key",
        "X-Tenant-ID": "Squad_Alpha"
    }

    for model in providers:
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": f"Test prompt for {model}"}]
        }
        resp = httpx.post(url, headers=headers, json=payload, timeout=10.0)
        assert resp.status_code == 200, f"Failed chat completions for model {model}: {resp.text}"
        data = resp.json()
        assert "choices" in data, f"No choices in response for {model}: {data}"
        assert len(data["choices"]) > 0
        assert data["model"] == model
        assert "usage" in data

def test_gateway_models_list_via_gateway():
    """
    Verify /v1/models endpoint via Envoy Gateway.
    """
    url = "http://127.0.0.1:8088/v1/models"
    headers = {"Host": "ai-gateway.localhost"}
    resp = httpx.get(url, headers=headers, timeout=10.0)
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("object") == "list"
    model_ids = [m["id"] for m in data.get("data", [])]
    assert "ollama/llama3.2" in model_ids
    assert "openai/gpt-4o-mini" in model_ids
