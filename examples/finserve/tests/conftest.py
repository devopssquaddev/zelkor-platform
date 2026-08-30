import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))


@pytest.fixture(scope="session")
def kubecontext():
    if os.environ.get("KUBECONTEXT"):
        return os.environ["KUBECONTEXT"]
    try:
        res = subprocess.run(
            ["kubectl", "config", "current-context"],
            capture_output=True,
            text=True,
            check=True,
        )
        ctx = res.stdout.strip()
        if ctx:
            return ctx
    except Exception:
        pass
    return "kind-zelkor"
