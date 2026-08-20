import pytest
import subprocess
import json

def test_gvisor_runtime_class_exists(kubecontext):
    """
    Verify RuntimeClass gvisor is defined in the cluster.
    """
    res = subprocess.run(
        ["kubectl", "--context", kubecontext, "get", "runtimeclass", "-o", "json"],
        capture_output=True,
        text=True
    )
    if res.returncode != 0:
        pytest.skip("RuntimeClass not supported or cluster inaccessible")

    data = json.loads(res.stdout)
    rc_names = [rc["metadata"]["name"] for rc in data.get("items", [])]
    assert "gvisor" in rc_names, f"Expected 'gvisor' RuntimeClass, found: {rc_names}"
