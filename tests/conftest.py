import pytest
import subprocess
import json
import time

@pytest.fixture(scope="session")
def kubecontext():
    """Returns the active or kind-zelkor kube context."""
    return "kind-zelkor"

@pytest.fixture(scope="session")
def cluster_pods(kubecontext):
    """Retrieves all pods from the cluster."""
    try:
        res = subprocess.run(
            ["kubectl", "--context", kubecontext, "get", "pods", "-o", "json"],
            capture_output=True,
            text=True,
            check=True
        )
        data = json.loads(res.stdout)
        return data.get("items", [])
    except Exception as e:
        pytest.skip(f"Kubernetes cluster not accessible: {e}")
