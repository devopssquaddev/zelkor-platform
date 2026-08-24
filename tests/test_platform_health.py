import pytest
import subprocess
import json

def test_platform_pods_running(kubecontext):
    """
    Verify all platform pods are in Running or Completed state.
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
    assert len(items) > 0, "No pods found in cluster"

    expected_components = ["postgresql", "valkey", "clickhouse", "qdrant", "ai-gateway", "langfuse", "aegra"]
    pod_names = [p["metadata"]["name"] for p in items]

    for comp in expected_components:
        matching = [name for name in pod_names if comp in name]
        assert len(matching) > 0, f"Expected pod for component '{comp}' not found in cluster (pods: {pod_names})"

    for pod in items:
        phase = pod["status"].get("phase")
        name = pod["metadata"]["name"]
        # Jobs can be Succeeded
        assert phase in ["Running", "Succeeded"], f"Pod {name} is in unexpected phase: {phase}"
