import os
import subprocess
import json
import sys
from pathlib import Path

import pytest

# Mirror Aegra image layout: flat `jwt_verifier` beside `tenant_auth`.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT / "mcp") not in sys.path:
    sys.path.insert(0, str(_ROOT / "mcp"))
import common.jwt_verifier as _jwt_verifier_module  # noqa: E402

sys.modules.setdefault("jwt_verifier", _jwt_verifier_module)

# CE-19e: bind S-gate JUnit evidence to the release it tested (read by scripts/release/fail_closed_matrix.py).
_EVIDENCE_ENV = {"zelkor_release": "ZELKOR_SGATE_VERSION", "zelkor_git_sha": "ZELKOR_SGATE_GIT_SHA",
                 "zelkor_run_id": "ZELKOR_SGATE_RUN_ID", "zelkor_profile": "ZELKOR_SGATE_PROFILE"}


@pytest.fixture(scope="session", autouse=True)
def _release_evidence_properties(record_testsuite_property):
    for name, env in _EVIDENCE_ENV.items():
        if os.environ.get(env):
            record_testsuite_property(name, os.environ[env])


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
