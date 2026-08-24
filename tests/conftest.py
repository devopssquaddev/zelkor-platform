import os
import subprocess
import json
import pytest

@pytest.fixture(scope="session")
def kubecontext():
    """
    Returns the target Kubernetes context:
    1. KUBECONTEXT environment variable if set.
    2. Current active context from `kubectl config current-context`.
    3. Fallback to 'kind-zelkor'.
    """
    if os.environ.get("KUBECONTEXT"):
        return os.environ["KUBECONTEXT"]
    try:
        res = subprocess.run(
            ["kubectl", "config", "current-context"],
            capture_output=True,
            text=True,
            check=True
        )
        ctx = res.stdout.strip()
        if ctx:
            return ctx
    except Exception:
        pass
    return "kind-zelkor"

@pytest.fixture(scope="session")
def gateway_base_url():
    """Returns the Gateway base URL (default: http://127.0.0.1:8088)."""
    return os.environ.get("GATEWAY_BASE_URL", "http://127.0.0.1:8088")

@pytest.fixture(scope="session")
def cluster_pods(kubecontext):
    """Retrieves all pods from the cluster across all namespaces."""
    try:
        res = subprocess.run(
            ["kubectl", "--context", kubecontext, "get", "pods", "-A", "-o", "json"],
            capture_output=True,
            text=True,
            check=True
        )
        data = json.loads(res.stdout)
        return data.get("items", [])
    except Exception as e:
        pytest.skip(f"Kubernetes cluster not accessible: {e}")
