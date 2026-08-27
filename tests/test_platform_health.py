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
    if len(items) == 0:
        pytest.skip("No pods found in cluster")

    expected_components = ["postgresql", "valkey", "clickhouse", "qdrant", "seaweedfs", "ai-gateway", "langfuse", "aegra"]
    pod_names = [p["metadata"]["name"] for p in items]

    if not any("zelkor" in name or "postgresql" in name for name in pod_names):
        pytest.skip(f"Platform pods not found in current cluster context '{kubecontext}' (likely testing via Gateway tunnel)")

    for comp in expected_components:
        matching = [name for name in pod_names if comp in name]
        assert len(matching) > 0, f"Expected pod for component '{comp}' not found in cluster (pods: {pod_names})"

    for pod in items:
        if "zelkor" in pod["metadata"]["name"] or any(comp in pod["metadata"]["name"] for comp in expected_components):
            phase = pod["status"].get("phase")
            name = pod["metadata"]["name"]
            # Jobs can be Succeeded
            assert phase in ["Running", "Succeeded"], f"Pod {name} is in unexpected phase: {phase}"
