"""Langfuse public API helpers for Gate A agent-trace assertions.

Langfuse 4.24 `events_only` removes GET /api/public/traces. Reads go through
GET /api/public/v2/observations, grouped by traceId.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import pytest

GATEWAY_BASE_URL = os.environ.get("GATEWAY_BASE_URL", "http://127.0.0.1:8088")
LANGFUSE_HOST_HEADER = os.environ.get("LANGFUSE_HOST_HEADER", "langfuse.localhost")
V2_FIELDS = "core,basic,io,trace_context"


def langfuse_auth() -> tuple[str, str]:
    """Read keys at call time so FinServe conftest / demo-tour env apply."""
    return (
        os.environ.get("LANGFUSE_PUBLIC_KEY", "pk-lf-zelkor-dev-00000000000000000000"),
        os.environ.get("LANGFUSE_SECRET_KEY", "sk-lf-zelkor-dev-00000000000000000000"),
    )


def langfuse_headers() -> dict[str, str]:
    return {"Host": LANGFUSE_HOST_HEADER}


def wait_for_llm_connection(name: str = "zelkor-ai-gateway", timeout: float = 120.0) -> bool:
    """Poll until surfaces seed Job has created the LLM connection (install does not wait on the Job)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = langfuse_get("/api/public/llm-connections")
        except httpx.ConnectError:
            time.sleep(2)
            continue
        if resp.status_code == 200:
            rows = resp.json().get("data") or resp.json()
            if isinstance(rows, dict):
                rows = rows.get("data") or [rows]
            names = [r.get("provider") or r.get("name") for r in rows]
            if name in names:
                return True
        time.sleep(2)
    return False


def langfuse_get(path: str, params: dict[str, Any] | None = None) -> httpx.Response:
    return httpx.get(
        f"{GATEWAY_BASE_URL}{path}",
        headers=langfuse_headers(),
        auth=langfuse_auth(),
        params=params,
        timeout=20.0,
    )


def observation_io_nonempty(payload: Any) -> bool:
    if payload is None or payload == "" or payload == {} or payload == []:
        return False
    if isinstance(payload, dict) and not any(payload.values()):
        return False
    return True


def _from_start_time(minutes: int = 10) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")


def list_observations(
    *,
    limit: int = 100,
    trace_id: str | None = None,
    name: str | None = None,
    session_id: str | None = None,
    user_id: str | None = None,
) -> list[dict]:
    params: dict[str, Any] = {
        "limit": min(limit, 80),
        "fields": V2_FIELDS if trace_id else "core,basic,trace_context",
        "fromStartTime": _from_start_time(3 if session_id or trace_id else 8),
    }
    filters: list[dict] = []
    if name:
        filters.append({"type": "string", "column": "traceName", "operator": "=", "value": name})
    if session_id:
        params["sessionId"] = session_id
    if trace_id:
        params["traceId"] = trace_id
    if user_id:
        params["userId"] = user_id
    if filters:
        params["filter"] = json.dumps(filters)
    try:
        resp = langfuse_get("/api/public/v2/observations", params=params)
    except httpx.ConnectError:
        pytest.skip(f"Langfuse not reachable at {GATEWAY_BASE_URL}")
    if resp.status_code != 200 and "timed out" in resp.text.lower():
        params["fromStartTime"] = _from_start_time(2)
        params["limit"] = min(int(params["limit"]), 20)
        params["fields"] = "core,basic,trace_context"
        params.pop("filter", None)
        resp = langfuse_get("/api/public/v2/observations", params=params)
    if resp.status_code != 200 and "timed out" in resp.text.lower():
        pytest.skip(f"Langfuse observations query timed out: {resp.text[:200]}")
    assert resp.status_code == 200, resp.text
    return resp.json().get("data") or []


def _traces_from_observations(rows: list[dict]) -> list[dict]:
    grouped: dict[str, dict] = {}
    for obs in rows:
        tid = obs.get("traceId")
        if not tid:
            continue
        tr = grouped.setdefault(
            tid,
            {
                "id": tid,
                "name": "",
                "sessionId": "",
                "userId": "",
                "metadata": {},
                "observations": [],
            },
        )
        if obs.get("traceName"):
            tr["name"] = obs["traceName"]
        if obs.get("sessionId"):
            tr["sessionId"] = obs["sessionId"]
        if obs.get("userId"):
            tr["userId"] = obs["userId"]
        tr["observations"].append(obs)
    return list(grouped.values())


def list_traces(
    *,
    limit: int = 50,
    name: str | None = None,
    session_id: str | None = None,
    user_id: str | None = None,
) -> list[dict]:
    rows = list_observations(limit=min(max(limit * 3, 30), 80), name=name, session_id=session_id, user_id=user_id)
    traces = _traces_from_observations(rows)
    return traces[:limit]


def trace_detail(trace_id: str) -> dict:
    rows = list_observations(limit=100, trace_id=trace_id)
    traces = _traces_from_observations(rows)
    if traces:
        return traces[0]
    return {"id": trace_id, "observations": []}


def trace_observations(detail: dict) -> list[dict]:
    # Always re-fetch by traceId so fields include io (list_traces omits io).
    trace_id = detail.get("id")
    if not trace_id:
        return detail.get("observations") or []
    return list_observations(limit=100, trace_id=trace_id)


def wait_for_traces(predicate, *, timeout: float = 45.0, **list_kwargs) -> list[dict]:
    deadline = time.time() + timeout
    last: list[dict] = []
    while time.time() < deadline:
        last = list_traces(limit=50, **list_kwargs)
        matched = [t for t in last if predicate(t)]
        if matched:
            return matched
        time.sleep(2)
    return []


def _observation_blob(obs: dict) -> str:
    return f"{obs.get('statusMessage') or ''} {obs.get('output') or ''} {obs.get('input') or ''}"


def failed_tool_observations(rows: list[dict]) -> list[dict]:
    """Tool spans whose output reports MCP/tool failure (may be level DEFAULT)."""
    bad = []
    for obs in rows:
        name = str(obs.get("name") or "")
        if obs.get("type") not in ("TOOL", "tool") and "tool" not in name.lower():
            continue
        blob = _observation_blob(obs).lower()
        if any(
            token in blob
            for token in ("mcperror", "password authentication failed", '"status": "error"')
        ):
            if "blocked" in blob or "refused" in blob or "content_safety" in blob:
                continue
            bad.append(obs)
    return bad


def unexpected_error_observations(rows: list[dict] | None = None) -> list[dict]:
    """ERROR-level observations and failed tool outputs (not guardrail refusals)."""
    if rows is None:
        rows = list_observations(limit=100)
    bad = []
    seen: set[str] = set()
    for obs in rows:
        oid = str(obs.get("id") or id(obs))
        level = str(obs.get("level") or "").upper()
        blob = _observation_blob(obs).lower()
        is_bad = level == "ERROR" or "exception" in blob or "traceback" in blob
        if is_bad:
            if "blocked" in blob or "refused" in blob or "content_safety" in blob:
                continue
            if oid not in seen:
                seen.add(oid)
                bad.append(obs)
    for obs in failed_tool_observations(rows):
        oid = str(obs.get("id") or id(obs))
        if oid not in seen:
            seen.add(oid)
            bad.append(obs)
    return bad


def has_execute_tool_span(observations: list) -> bool:
    for obs in observations:
        if str(obs.get("name") or "") == "execute":
            return True
    return False


def has_sandbox_mcp_span(observations: list) -> bool:
    for obs in observations:
        if str(obs.get("name") or "") == "sandbox__execute_python":
            return True
    return False


def _observation_metadata(obs: dict) -> dict:
    meta = obs.get("metadata")
    if isinstance(meta, dict):
        return meta
    if isinstance(meta, str):
        try:
            parsed = json.loads(meta)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def sandbox_execution_metadata(observations: list) -> dict | None:
    """Return sandbox outcome/violation from TOOL observation metadata if present."""
    for obs in observations:
        if obs.get("type") not in ("TOOL", "tool"):
            continue
        name = str(obs.get("name") or "")
        if name not in ("sandbox__execute_python", "execute"):
            continue
        meta = _observation_metadata(obs)
        sandbox_meta = meta.get("sandbox") if isinstance(meta.get("sandbox"), dict) else meta
        outcome = (
            meta.get("sandbox.outcome")
            or (sandbox_meta or {}).get("outcome")
            or meta.get("sandbox_outcome")
        )
        violation = (
            meta.get("sandbox.violation")
            or (sandbox_meta or {}).get("violation")
            or meta.get("sandbox_violation")
        )
        text = _observation_blob(obs)
        if not outcome and "sandbox.outcome" in text:
            for token in ("denied", "suspicious", "allowed", "exploit"):
                if token in text:
                    outcome = token
                    break
        if outcome or violation:
            return {
                "outcome": outcome,
                "violation": violation,
                "name": name,
            }
    return None


def blob(value: Any) -> str:
    return str(value).lower()


def has_graph_spans(observations: list, detail: dict) -> bool:
    text = blob(observations) + blob(detail)
    return any(token in text for token in ("langgraph", "openinference", "create_agent", "chatopenai"))


def has_nemo_spans(observations: list, detail: dict) -> bool:
    text = blob(observations) + blob(detail)
    return any(token in text for token in ("nemo", "guardrails", "content_safety"))


def is_health_probe_trace(trace: dict, observations: list | None = None) -> bool:
    name = str(trace.get("name") or "")
    return "/v1/health" in name


def is_orphan_http_client_trace(trace: dict, observations: list | None = None) -> bool:
    """Untitled one-span http send/receive (NeMo CLIENT root)."""
    rows = observations if observations is not None else trace.get("observations") or []
    if not rows:
        return False
    if any(o.get("parentObservationId") for o in rows if isinstance(o, dict)):
        return False
    names = [str(o.get("name") or "").lower() for o in rows if isinstance(o, dict)]
    if not names:
        return False
    return all("http send" in n or "http receive" in n for n in names)


def graph_root_output_is_assistant(output: Any) -> bool:
    text = str(output or "")
    if not observation_io_nonempty(output):
        return False
    return '"type": "checkpoint"' not in text and '"type":"checkpoint"' not in text


def recent_orphan_http_client_ids(*, since_iso: str, limit: int = 100) -> list[str]:
    """Orphan CLIENT http send traces started at or after since_iso."""
    grouped: dict[str, list[dict]] = {}
    for obs in list_observations(limit=limit):
        tid = obs.get("traceId")
        if not tid:
            continue
        grouped.setdefault(tid, []).append(obs)
    out: list[str] = []
    for tid, rows in grouped.items():
        if not is_orphan_http_client_trace({"id": tid}, rows):
            continue
        starts = [str(o.get("startTime") or "") for o in rows]
        if any(ts >= since_iso for ts in starts if ts):
            out.append(tid)
    return out
