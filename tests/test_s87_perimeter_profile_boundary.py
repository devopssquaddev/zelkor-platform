"""S-87: a live `profile=perimeter` install is boundary-only and fits the budget.

Needs KUBECONTEXT; reads the platform's mode from its discovery contract in
ZELKOR_PLATFORM_NAMESPACE and skips unless PROFILE=perimeter. Asserts no stateful workload runs
(the opted-in NeMo / sandbox / data-tool planes, GUARDRAILS_ENABLED / SANDBOX_ENABLED /
MCP_BACKENDS in the contract, are allowed) and, for the default perimeter without opt-ins, summed pod RSS is under 500 MB.
The `<90s` install time is measured by the installer, not
here; the rendered-manifest boundary (no datastores/Langfuse/Aegra/NeMo/data-MCP) is covered
offline by tests/test_profile_perimeter.py.
"""
from __future__ import annotations

import json
import os
import re

import pytest

from tests.helpers.kube import kubectl_run, platform_contract
from tests.helpers.runtime_agents import require_kube

FORBIDDEN = ("postgresql", "clickhouse", "valkey", "qdrant", "seaweedfs",
             "langfuse", "aegra", "nemo", "mcp-postgres", "mcp-qdrant", "mcp-sandbox")
RSS_BUDGET_MI = 500


REL = os.environ.get("ZELKOR_PLATFORM_RELEASE", "zelkor-platform")
# Opted-in planes (contract) -> the pod-name prefixes they add; none holds a datastore.
OPT_INS = {"GUARDRAILS_ENABLED": ("nemo",), "SANDBOX_ENABLED": ("mcp-sandbox",)}
DATA_TOOLS = {"postgres": "mcp-postgres", "qdrant": "mcp-qdrant"}  # perimeter.dataTools


def _contract() -> tuple[str, dict]:
    ns = os.environ.get("ZELKOR_PLATFORM_NAMESPACE", "zelkor")
    contract = platform_contract(ns)
    profile = contract.get("PROFILE", "")
    if profile != "perimeter":
        pytest.skip(f"platform in {ns} is not profile=perimeter (contract PROFILE={profile or 'absent'})")
    return ns, contract


def _opted_in(contract: dict) -> tuple[str, ...]:
    """Pod-name prefixes of the opted-in planes."""
    planes = [tok for key, toks in OPT_INS.items() if contract.get(key) == "true" for tok in toks]
    backends = {b.strip() for b in contract.get("MCP_BACKENDS", "").split(",")}
    planes += [pod for backend, pod in DATA_TOOLS.items() if backend in backends]
    return tuple(f"{REL}-{p}" for p in planes)


def test_no_stateful_workload_runs_in_the_perimeter():
    require_kube()
    ns, contract = _contract()
    allowed = _opted_in(contract)
    res = kubectl_run(["get", "pods", "-o", "json"], namespace=ns)
    assert res.returncode == 0, res.stderr
    names = [p["metadata"]["name"] for p in json.loads(res.stdout).get("items", [])]
    assert names, f"no pods in {ns}"
    offenders = [n for n in names if any(tok in n for tok in FORBIDDEN) and not n.startswith(allowed)]
    assert not offenders, f"stateful workloads present in a zero-DB perimeter: {offenders}"


def test_perimeter_fits_the_memory_budget():
    require_kube()
    ns, contract = _contract()
    if _opted_in(contract):
        pytest.skip("the memory budget is for the default perimeter (a plane is opted in)")
    res = kubectl_run(["top", "pods", "--containers", "--no-headers"], namespace=ns)
    if res.returncode != 0:
        pytest.skip(f"kubectl top unavailable (metrics-server?): {res.stderr.strip()[:200]}")
    # Zelkor's footprint: platform pods plus the sidecar wrapped around each agent. The customer's
    # own `agent` container is their code, not the perimeter's budget.
    total_mi = 0
    for line in res.stdout.splitlines():
        cols = line.split()
        m = re.search(r"(\d+)Mi\b", line)
        if m and len(cols) >= 2 and cols[1] != "agent":
            total_mi += int(m.group(1))
    assert 0 < total_mi < RSS_BUDGET_MI, f"perimeter RSS {total_mi}Mi exceeds {RSS_BUDGET_MI}Mi budget"
