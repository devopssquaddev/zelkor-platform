import pytest
import subprocess
import json

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
