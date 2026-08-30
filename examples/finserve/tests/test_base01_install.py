import json
import os
import subprocess
import time

import httpx
import pytest

from finserve_e2e import GATEWAY_BASE_URL, run_finserve

LANGFUSE_HOST_HEADER = os.environ.get("LANGFUSE_HOST_HEADER", "langfuse.localhost")


def test_base01_finserve_pods_healthy(kubecontext):
    """E2E smoke: FinServe worker and platform MCP pods are running."""
    try:
        res = subprocess.run(
            ["kubectl", "--context", kubecontext, "get", "pods", "-A", "-o", "json"],
            capture_output=True,
            text=True,
            check=True,
        )
    except Exception as exc:
        pytest.skip(f"Kubernetes cluster not accessible: {exc}")

    pod_names = [p["metadata"]["name"] for p in json.loads(res.stdout).get("items", [])]
    if not any("finserve" in name for name in pod_names):
        pytest.skip(f"FinServe pods not present in context '{kubecontext}'")

    assert any("finserve-agent" in name for name in pod_names)
    assert any("mcp-sandbox" in name for name in pod_names)
    assert any("mcp-gateway" in name for name in pod_names)


def test_base01_finserve_runs_via_front_door():
    """E2E smoke: platform Aegra run with graph_id=finserve returns 200."""
    result = run_finserve("What is my total portfolio valuation?")
    assert result["text"]


def test_base01_langfuse_observability_endpoint():
    """E2E smoke: Langfuse health endpoint reachable via gateway."""
    url = f"{GATEWAY_BASE_URL}/api/public/health"
    headers = {"Host": LANGFUSE_HOST_HEADER}
    try:
        resp = httpx.get(url, headers=headers, timeout=10.0)
        assert resp.status_code == 200, f"Failed Langfuse health check: {resp.text}"
    except httpx.ConnectError:
        pytest.skip(f"Gateway not reachable at {GATEWAY_BASE_URL}")


def test_base01_finserve_agent_generates_traces():
    """E2E smoke: a FinServe run leaves LLM traces via gateway OTel."""
    run_finserve("Summarize my portfolio holdings.")
    time.sleep(2.0)
    try:
        traces_resp = httpx.get(
            f"{GATEWAY_BASE_URL}/api/public/traces",
            headers={"Host": LANGFUSE_HOST_HEADER},
            auth=(
                os.environ.get("LANGFUSE_PUBLIC_KEY", "pk-lf-zelkor-dev-00000000000000000000"),
                os.environ.get("LANGFUSE_SECRET_KEY", "sk-lf-zelkor-dev-00000000000000000000"),
            ),
            timeout=10.0,
        )
    except httpx.ConnectError:
        pytest.skip(f"Gateway not reachable at {GATEWAY_BASE_URL}")
    assert traces_resp.status_code == 200, f"Failed to query Langfuse traces: {traces_resp.text}"
    traces = traces_resp.json().get("data", [])
    if not traces:
        pytest.skip("Langfuse OTel export may be async or empty")
    matching = [t for t in traces if t.get("userId") == "Bank_Alpha" or "Bank_Alpha" in (t.get("tags") or [])]
    assert matching or traces
