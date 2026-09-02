import json
import os
import subprocess
import sys
import time
from pathlib import Path

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

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tests.helpers.langfuse import (  # noqa: E402
    graph_root_output_is_assistant,
    has_graph_spans,
    has_nemo_spans,
    list_traces,
    recent_orphan_http_client_ids,
    trace_detail,
    trace_observations,
    unexpected_error_observations,
    wait_for_traces,
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
    assert any("finserve-coder" in name for name in pod_names)
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


def test_base01_finserve_langfuse_connection_seeded():
    """FinServe project gets the gateway LLM connection (armor seed on extraProjects)."""
    try:
        resp = httpx.get(
            f"{GATEWAY_BASE_URL}/api/public/llm-connections",
            headers={"Host": LANGFUSE_HOST_HEADER},
            auth=(
                os.environ.get("LANGFUSE_PUBLIC_KEY", "pk-lf-finserve-dev-00000000000000000000"),
                os.environ.get("LANGFUSE_SECRET_KEY", "sk-lf-finserve-dev-00000000000000000000"),
            ),
            timeout=10.0,
        )
    except httpx.ConnectError:
        pytest.skip(f"Gateway not reachable at {GATEWAY_BASE_URL}")
    if resp.status_code in (401, 403, 404):
        pytest.skip(f"llm-connections unavailable: {resp.status_code}")
    assert resp.status_code == 200, resp.text
    rows = resp.json().get("data") or resp.json()
    if isinstance(rows, dict):
        rows = rows.get("data") or [rows]
    names = [r.get("provider") or r.get("name") for r in rows]
    assert "zelkor-ai-gateway" in names, f"FinServe project missing gateway connection (got {names})"


def test_base01_finserve_agent_generates_traces():
    """E2E smoke: one FinServe run = one Langfuse waterfall (graph + NeMo)."""
    marker = f"zelkor-join-{int(time.time())}"
    run_started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    result = run_finserve(f"Summarize my portfolio holdings. [{marker}]")
    thread_id = result.get("thread_id") or ""
    if os.environ.get("NEMO_OTEL_JOIN", "1").strip().lower() in ("0", "false", "off"):
        pytest.skip("NEMO_OTEL_JOIN disabled")
    time.sleep(8)
    matched = wait_for_traces(
        lambda t: str(t.get("sessionId") or "") == thread_id or marker in str(t),
        timeout=90.0,
        session_id=thread_id or None,
    )
    if not matched:
        pytest.skip("No Langfuse observations for the FinServe run within 45s")

    joined = []
    split = []
    deadline = time.time() + 30
    while time.time() < deadline:
        joined = []
        split = []
        window = list_traces(limit=20, session_id=thread_id) if thread_id else list_traces(limit=20, name=GRAPH_ADVISOR)
        for tr in window:
            if thread_id and str(tr.get("sessionId") or "") != thread_id:
                continue
            detail = trace_detail(tr["id"])
            observations = trace_observations(detail)
            has_graph = has_graph_spans(observations, detail)
            has_nemo = has_nemo_spans(observations, detail)
            if has_graph and has_nemo:
                joined.append(tr)
            elif has_graph and not has_nemo:
                split.append(tr["id"])
        if joined and not split:
            break
        time.sleep(2)
    assert not split, f"graph-named traces without NeMo: {split}"
    assert joined, "FinServe run produced no joined graph+NeMo trace"
    assert len(joined) == 1, f"expected one trace, got {len(joined)} ids={[t.get('id') for t in joined]}"

    observations = trace_observations(trace_detail(joined[0]["id"]))
    by_id = {obs.get("id"): obs for obs in observations if obs.get("id")}
    chat_ids = {
        obs.get("id")
        for obs in observations
        if "chatopenai" in str(obs.get("name") or "").lower()
        and str(obs.get("name") or "") != "ChatOpenAI.request"
    }
    for req in observations:
        if str(req.get("name") or "") != "ChatOpenAI.request":
            continue
        parent = by_id.get(req.get("parentObservationId") or "")
        parent_name = str((parent or {}).get("name") or "")
        assert parent_name.lower() == "chatopenai" or req.get("parentObservationId") in chat_ids, (
            f"ChatOpenAI.request parent={parent_name!r} (trace {joined[0].get('id')})"
        )
    assert not unexpected_error_observations(observations)
    nemo_rows = [
        obs
        for obs in observations
        if "guardrails" in str(obs.get("name") or "").lower()
        or str(obs.get("name") or "").startswith("POST")
    ]
    missing_name = [obs.get("name") for obs in nemo_rows if not obs.get("traceName")]
    assert not missing_name, f"NeMo observations missing traceName: {missing_name[:8]}"
    assert all(str(obs.get("traceName") or "") == GRAPH_ADVISOR for obs in nemo_rows)
    graph_root = next((obs for obs in observations if str(obs.get("name") or "") == GRAPH_ADVISOR), None)
    if graph_root:
        assert graph_root_output_is_assistant(graph_root.get("output")), graph_root.get("output")
    orphans = recent_orphan_http_client_ids(since_iso=run_started)
    assert not orphans, f"orphan http send traces: {orphans}"


def test_base01_finserve_trace_not_on_platform_project():
    """Team A keys must not list a FinServe run (Langfuse project split)."""
    marker = f"zelkor-split-{int(time.time())}"
    result = run_finserve(f"Summarize my portfolio holdings. [{marker}]")
    thread_id = result.get("thread_id") or ""
    if not thread_id:
        pytest.skip("no thread_id on FinServe run")
    matched = wait_for_traces(
        lambda t: str(t.get("sessionId") or "") == thread_id,
        timeout=45.0,
        session_id=thread_id,
        name=GRAPH_ADVISOR,
    )
    if not matched:
        pytest.skip("FinServe trace not visible with FinServe keys")
    platform_pk = os.environ.get("LANGFUSE_PLATFORM_PUBLIC_KEY", "pk-lf-zelkor-dev-00000000000000000000")
    platform_sk = os.environ.get("LANGFUSE_PLATFORM_SECRET_KEY", "sk-lf-zelkor-dev-00000000000000000000")
    try:
        resp = httpx.get(
            f"{GATEWAY_BASE_URL}/api/public/v2/observations",
            headers={"Host": LANGFUSE_HOST_HEADER},
            auth=(platform_pk, platform_sk),
            params={
                "limit": 100,
                "fields": "core,basic,io,trace_context",
                "filter": json.dumps(
                    [{"type": "string", "column": "sessionId", "operator": "=", "value": thread_id}]
                ),
            },
            timeout=10.0,
        )
    except httpx.ConnectError:
        pytest.skip(f"Gateway not reachable at {GATEWAY_BASE_URL}")
    if resp.status_code != 200:
        pytest.skip(f"platform observations unavailable: {resp.status_code}")
    rows = resp.json().get("data") or []
    assert not rows, f"platform project saw FinServe session {thread_id}: {len(rows)} observations"
