"""FinServe seed Job must be admitted by the platform Langfuse NetworkPolicy (no cluster)."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

CHART = Path(__file__).resolve().parents[1] / "chart"


def _seed_job() -> dict:
    if not shutil.which("helm"):
        pytest.skip("helm not installed")
    out = subprocess.run(
        ["helm", "template", "finserve", str(CHART), "--show-only", "templates/job-langfuse-seed.yaml",
         "-f", str(CHART / "values-local.yaml")],
        check=True, capture_output=True, text=True,
    ).stdout
    return next(d for d in yaml.safe_load_all(out) if d and d.get("kind") == "Job")


def test_seed_pod_carries_agent_workload_label():
    # zelkor-platform-langfuse-dest-deny admits zelkor.io/workload-type=agent; the platform
    # agent-egress policy then limits the seed to DNS, gateways, guardrails and Langfuse.
    labels = _seed_job()["spec"]["template"]["metadata"]["labels"]
    assert labels.get("zelkor.io/workload-type") == "agent"


def test_seed_needs_no_package_index():
    # Agent egress has no internet route, so a runtime pip install hangs or fails.
    script = " ".join(_seed_job()["spec"]["template"]["spec"]["containers"][0]["command"])
    assert "pip install" not in script
    assert "import requests" not in script
