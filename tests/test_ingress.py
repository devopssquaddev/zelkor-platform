import pytest
import subprocess
import json
import httpx
import time

def test_ingress_controller_running(kubecontext):
    """
    Verify ingress-nginx controller is running in the cluster.
    """
    res = subprocess.run(
        ["kubectl", "--context", kubecontext, "get", "pods", "-n", "ingress-nginx", "-o", "json"],
        capture_output=True,
        text=True,
        check=True
    )
    data = json.loads(res.stdout)
    items = data.get("items", [])
    assert len(items) > 0, "No ingress-nginx pods found"

    controller_pods = [p for p in items if "ingress-nginx-controller" in p["metadata"]["name"]]
    assert len(controller_pods) > 0, "ingress-nginx controller pod not found"

    for pod in controller_pods:
        phase = pod["status"].get("phase")
        assert phase == "Running", f"Ingress controller pod not in Running phase: {phase}"

def test_ingress_resources_configured(kubecontext):
    """
    Verify platform and demo Ingress resources exist with expected host rules.
    """
    res = subprocess.run(
        ["kubectl", "--context", kubecontext, "get", "ingress", "-A", "-o", "json"],
        capture_output=True,
        text=True,
        check=True
    )
    data = json.loads(res.stdout)
    items = data.get("items", [])
    ingress_names = [i["metadata"]["name"] for i in items]

    assert any("zelkor-platform" in name for name in ingress_names), "zelkor-platform ingress not found"

    all_hosts = []
    for ing in items:
        for rule in ing.get("spec", {}).get("rules", []):
            if "host" in rule:
                all_hosts.append(rule["host"])

    assert "langfuse.localhost" in all_hosts, f"langfuse.localhost not in {all_hosts}"
    assert "litellm.localhost" in all_hosts, f"litellm.localhost not in {all_hosts}"
    assert "aegra.localhost" in all_hosts, f"aegra.localhost not in {all_hosts}"

def test_ingress_routing_http_endpoints():
    """
    Verify HTTP routing through localhost:8088 via Host headers.
    """
    endpoints = [
        ("langfuse.localhost", "/api/public/health"),
        ("litellm.localhost", "/health/liveliness"),
        ("aegra.localhost", "/health"),
        ("finserve.localhost", "/health"),
    ]

    for host, path in endpoints:
        url = f"http://127.0.0.1:8088{path}"
        headers = {"Host": host}
        
        # Retry briefly for Ingress sync
        success = False
        last_error = None
        for _ in range(10):
            try:
                resp = httpx.get(url, headers=headers, timeout=5.0)
                if resp.status_code == 200:
                    success = True
                    break
            except Exception as e:
                last_error = e
            time.sleep(1)

        assert success, f"Failed to reach {host}{path} via Ingress on port 8088: {last_error}"
