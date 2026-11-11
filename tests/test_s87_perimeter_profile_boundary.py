"""S-87: a live `profile=perimeter` install is boundary-only and fits the budget.

Needs KUBECONTEXT and PERIMETER_NAMESPACE (the namespace of a `profile=perimeter`
install). Asserts no stateful workload runs and summed pod RSS is under 500 MB.
The `<90s` install time is measured by the installer, not here; the rendered-manifest
boundary (no datastores/Langfuse/Aegra/NeMo/data-MCP) is covered offline by
tests/test_profile_perimeter.py.
"""
from __future__ import annotations

import json
import os
import re

import pytest

from tests.helpers.kube import kubectl_run
from tests.helpers.runtime_agents import require_kube

FORBIDDEN = ("postgresql", "clickhouse", "valkey", "qdrant", "seaweedfs",
             "langfuse", "aegra", "nemo", "mcp-postgres", "mcp-qdrant", "mcp-sandbox")
RSS_BUDGET_MI = 500


def _namespace() -> str:
    ns = os.environ.get("PERIMETER_NAMESPACE", "").strip()
    if not ns:
        pytest.skip("PERIMETER_NAMESPACE not set (namespace of a profile=perimeter install)")
    return ns


def test_no_stateful_workload_runs_in_the_perimeter():
    require_kube()
    ns = _namespace()
    res = kubectl_run(["get", "pods", "-o", "json"], namespace=ns)
    assert res.returncode == 0, res.stderr
    names = [p["metadata"]["name"] for p in json.loads(res.stdout).get("items", [])]
    assert names, f"no pods in {ns}"
    offenders = [n for n in names if any(tok in n for tok in FORBIDDEN)]
    assert not offenders, f"stateful workloads present in a zero-DB perimeter: {offenders}"


def test_perimeter_fits_the_memory_budget():
    require_kube()
    ns = _namespace()
    res = kubectl_run(["top", "pods", "--no-headers"], namespace=ns)
    if res.returncode != 0:
        pytest.skip(f"kubectl top unavailable (metrics-server?): {res.stderr.strip()[:200]}")
    total_mi = 0
    for line in res.stdout.splitlines():
        m = re.search(r"(\d+)Mi\b", line)
        if m:
            total_mi += int(m.group(1))
    assert 0 < total_mi < RSS_BUDGET_MI, f"perimeter RSS {total_mi}Mi exceeds {RSS_BUDGET_MI}Mi budget"
