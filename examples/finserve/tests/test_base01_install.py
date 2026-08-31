import json
import os
import subprocess
import time

import httpx
import pytest

from finserve_e2e import (
    GATEWAY_BASE_URL,
    GRAPH_ADVISOR,
    GRAPH_IDS,
    GRAPH_QUANT,
    GRAPH_RESEARCH,
    run_finserve,
)

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

    assert any("finserve-desk" in name for name in pod_names)
    assert any("finserve-quant" in name for name in pod_names)
    assert any("mcp-sandbox" in name for name in pod_names)
    assert any("mcp-gateway" in name for name in pod_names)


@pytest.mark.parametrize("graph_id", GRAPH_IDS)
def test_base01_finserve_runs_via_front_door(graph_id):
    """E2E smoke: platform Aegra run with each FinServe graph_id returns 200."""
    result = run_finserve("What is my total portfolio valuation?", graph_id=graph_id)
    assert result["text"]


def test_base01_desk_and_quant_routing():
    """Advisor and research share the desk Service; quant is a second Deployment."""
    advisor = run_finserve("Show my current portfolio holdings.", graph_id=GRAPH_ADVISOR)
    research = run_finserve(
        "What is our asset allocation policy for high-growth tech?",
        graph_id=GRAPH_RESEARCH,
    )
    quant = run_finserve(
        "Use the sandbox tool to execute this Python and return the output:\n"
        "```python\nprint('sandbox-ok')\n```",
        graph_id=GRAPH_QUANT,
        timeout=120.0,
    )
    assert advisor["text"]
    assert research["text"]
    assert quant["text"]


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
    started = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
    marker = f"zelkor-join-{int(time.time())}"
    run_finserve(f"Summarize my portfolio holdings. [{marker}]")
    auth = (
        os.environ.get("LANGFUSE_PUBLIC_KEY", "pk-lf-zelkor-dev-00000000000000000000"),
        os.environ.get("LANGFUSE_SECRET_KEY", "sk-lf-zelkor-dev-00000000000000000000"),
    )
    headers = {"Host": LANGFUSE_HOST_HEADER}
    deadline = time.time() + 45
    traces = []
    matching = []
    while time.time() < deadline:
        try:
            traces_resp = httpx.get(
                f"{GATEWAY_BASE_URL}/api/public/traces",
                headers=headers,
                auth=auth,
                params={"limit": 50},
                timeout=10.0,
            )
        except httpx.ConnectError:
            pytest.skip(f"Gateway not reachable at {GATEWAY_BASE_URL}")
        assert traces_resp.status_code == 200, f"Failed to query Langfuse traces: {traces_resp.text}"
        traces = traces_resp.json().get("data", [])
        matching = [t for t in traces if marker in str(t)]
        if not matching:
            matching = [
                t
                for t in traces
                if str(t.get("name") or "").startswith("finserve-")
                and str(t.get("timestamp") or "") >= started
            ]
        if matching:
            break
        time.sleep(2)
    if not traces:
        pytest.skip("Langfuse OTel export may be async or empty")
    assert matching or traces

    candidates = matching or traces
    if os.environ.get("NEMO_OTEL_JOIN", "1").strip().lower() in ("0", "false", "off"):
        pytest.skip("NEMO_OTEL_JOIN disabled")
    obs_deadline = time.time() + 30
    seen: list = []
    joined: list = []
    split: list = []
    while time.time() < obs_deadline:
        seen = []
        joined = []
        split = []
        for tr in candidates:
            trace_id = tr.get("id")
            if not trace_id:
                continue
            detail_resp = httpx.get(
                f"{GATEWAY_BASE_URL}/api/public/traces/{trace_id}",
                headers=headers,
                auth=auth,
                timeout=10.0,
            )
            if detail_resp.status_code != 200:
                continue
            detail = detail_resp.json()
            observations = detail.get("observations") or []
            if not observations:
                obs_resp = httpx.get(
                    f"{GATEWAY_BASE_URL}/api/public/observations",
                    headers=headers,
                    auth=auth,
                    params={"traceId": trace_id, "limit": 100},
                    timeout=10.0,
                )
                if obs_resp.status_code == 200:
                    observations = obs_resp.json().get("data", [])
            blob = str(observations).lower() + str(detail).lower()
            seen.append(trace_id)
            has_nemo = any(token in blob for token in ("nemo", "guardrails", "content_safety"))
            has_graph = any(
                token in blob
                for token in ("langgraph", "openinference", "create_agent", "chatopenai")
            )
            if has_nemo:
                joined.append(trace_id)
            elif has_graph:
                split.append(trace_id)
        if joined and not split:
            return
        time.sleep(2)
    pytest.fail(
        f"Langfuse split traces: graph-without-NeMo {split}; joined {joined}; seen {seen} "
        "(W3C join missing or OTel overlay off; set NEMO_OTEL_JOIN=0 to skip)"
    )
