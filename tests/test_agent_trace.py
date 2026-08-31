"""One Agent Protocol run = one Langfuse trace (graph + NeMo + observation I/O)."""
from __future__ import annotations

import os
import time
import uuid
from pathlib import Path

import httpx
import pytest

from tests.helpers.langfuse import (
    GATEWAY_BASE_URL,
    has_graph_spans,
    has_nemo_spans,
    is_health_probe_trace,
    list_traces,
    observation_io_nonempty,
    trace_detail,
    trace_observations,
    wait_for_traces,
)
from tests.helpers.langgraph_client import aegra_sdk_client

WORKER_GRAPH_ID = os.environ.get("AEGRA_WORKER_GRAPH_ID", "")
NEMO_HOST_HEADER = os.environ.get("NEMO_HOST_HEADER", "nemo.localhost")
ROOT = Path(__file__).resolve().parents[1]
PLATFORM_CHART = ROOT / "charts/zelkor-platform"
LOCAL_VALUES = ROOT / "profiles/values-local.yaml"


def _require_worker() -> str:
    if not WORKER_GRAPH_ID:
        pytest.skip("AEGRA_WORKER_GRAPH_ID not set (no test-local worker fixture)")
    return WORKER_GRAPH_ID


def _skip_if_unreachable(exc: BaseException) -> None:
    if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout)):
        pytest.skip(f"Aegra not reachable: {exc}")


def test_capture_content_chart_default_off_local_on():
    values = (PLATFORM_CHART / "values.yaml").read_text()
    nemo = values.split("guardrails:", 1)[1]
    assert "captureContent: false" in nemo.split("safetyRefusal", 1)[0]
    local = LOCAL_VALUES.read_text()
    assert "captureContent: true" in local
    excluded = (PLATFORM_CHART / "templates/_helpers.tpl").read_text()
    assert 'value: "/v1/health"' in excluded


def _classify(trace: dict) -> tuple[bool, bool, list]:
    detail = trace_detail(trace["id"])
    observations = trace_observations(detail)
    return has_graph_spans(observations, detail), has_nemo_spans(observations, detail), observations


def _session_of(trace: dict) -> str:
    return str(trace.get("sessionId") or trace.get("session_id") or "")


def _user_of(trace: dict) -> str:
    return str(trace.get("userId") or trace.get("user_id") or "")


def _window_for_run(graph_id: str, thread_id: str, marker: str) -> list[dict]:
    traces = list_traces(limit=50, name=graph_id)
    by_session = list_traces(limit=50, session_id=thread_id)
    seen = {t.get("id"): t for t in traces + by_session if t.get("id")}
    window = []
    for tr in seen.values():
        if _session_of(tr) == thread_id:
            window.append(tr)
            continue
        if marker in str(tr) and str(tr.get("name") or "") == graph_id:
            window.append(tr)
    return window


@pytest.mark.asyncio
async def test_agent_protocol_run_is_one_langfuse_trace():
    """§5: exactly one graph+NeMo trace; graph-named without NeMo fails."""
    graph_id = _require_worker()
    marker = f"zelkor-agent-trace-{uuid.uuid4().hex[:8]}"
    tenant = "tenant-a"
    client = aegra_sdk_client(tenant_id=tenant, graph_id=graph_id)
    try:
        thread = await client.threads.create()
        thread_id = thread["thread_id"]
        result = await client.runs.wait(
            thread_id=thread_id,
            assistant_id=graph_id,
            input={"messages": [{"role": "human", "content": f"Say ok. [{marker}]"}]},
        )
    except Exception as exc:
        _skip_if_unreachable(exc)
        raise
    assert result is not None

    matched = wait_for_traces(
        lambda t: _session_of(t) == thread_id or marker in str(t),
        timeout=45.0,
        name=graph_id,
    )
    if not matched:
        pytest.skip(
            "No Langfuse trace for the Agent Protocol run within 45s "
            "(OTel overlay off or ingest lag)"
        )

    joined = []
    split = []
    deadline = time.time() + 30
    while time.time() < deadline:
        joined = []
        split = []
        for tr in _window_for_run(graph_id, thread_id, marker):
            if not tr.get("id"):
                continue
            has_graph, has_nemo, _obs = _classify(tr)
            if has_graph and has_nemo:
                joined.append(tr)
            elif has_graph and not has_nemo:
                split.append(tr["id"])
        if joined and not split:
            break
        time.sleep(2)

    assert not split, (
        f"graph-named Langfuse traces without NeMo: {split} "
        "(W3C join missing; intercept/OTel overlay off)"
    )
    assert joined, "Agent Protocol run produced graph spans but no joined graph+NeMo trace"
    assert len(joined) == 1, (
        f"expected one Langfuse trace for this run, got {len(joined)} "
        f"ids={[t.get('id') for t in joined]}"
    )

    trace = joined[0]
    assert str(trace.get("name") or "") == graph_id
    assert _user_of(trace) == tenant, trace
    assert _session_of(trace) == thread_id, trace
    metadata = trace.get("metadata") or {}
    run_id = metadata.get("run_id")
    if run_id:
        assert isinstance(run_id, str) and run_id

    _, _, observations = _classify(trace)
    capture_off = os.environ.get("NEMO_OTEL_CAPTURE_CONTENT", "1").strip().lower() in (
        "0",
        "false",
        "off",
    )
    if capture_off:
        return
    generations = [
        obs
        for obs in observations
        if isinstance(obs, dict)
        and (
            str(obs.get("type") or "").upper() == "GENERATION"
            or "generation" in str(obs.get("name") or "").lower()
            or "chatopenai" in str(obs.get("name") or "").lower()
        )
    ]
    has_io = any(
        observation_io_nonempty(obs.get("input")) and observation_io_nonempty(obs.get("output"))
        for obs in (generations or observations)
        if isinstance(obs, dict)
    )
    assert has_io, (
        "captureContent is on but no GENERATION observation has input and output "
        f"(trace {trace.get('id')})"
    )


def test_nemo_health_probe_is_not_a_langfuse_trace():
    """§2 MUST NOT: /v1/health as traces."""
    url = f"{GATEWAY_BASE_URL}/v1/health"
    try:
        resp = httpx.get(url, headers={"Host": NEMO_HOST_HEADER}, timeout=10.0)
        if resp.status_code >= 500:
            pytest.skip(f"NeMo health failed: {resp.status_code}")
    except httpx.ConnectError:
        pytest.skip(f"NeMo not reachable at {GATEWAY_BASE_URL}")

    time.sleep(4)
    try:
        traces = list_traces(limit=50)
    except pytest.skip.Exception:
        raise
    except Exception as exc:
        pytest.skip(f"Langfuse not reachable: {exc}")

    probes = [t.get("id") or t.get("name") for t in traces if is_health_probe_trace(t)]
    assert not probes, f"NeMo /v1/health created Langfuse traces: {probes}"
