"""Langfuse public API helpers for Gate A agent-trace assertions."""
from __future__ import annotations

import os
import time
from typing import Any

import httpx
import pytest

GATEWAY_BASE_URL = os.environ.get("GATEWAY_BASE_URL", "http://127.0.0.1:8088")
LANGFUSE_HOST_HEADER = os.environ.get("LANGFUSE_HOST_HEADER", "langfuse.localhost")
LANGFUSE_AUTH = (
    os.environ.get("LANGFUSE_PUBLIC_KEY", "pk-lf-zelkor-dev-00000000000000000000"),
    os.environ.get("LANGFUSE_SECRET_KEY", "sk-lf-zelkor-dev-00000000000000000000"),
)


def langfuse_headers() -> dict[str, str]:
    return {"Host": LANGFUSE_HOST_HEADER}


def langfuse_get(path: str, params: dict[str, Any] | None = None) -> httpx.Response:
    return httpx.get(
        f"{GATEWAY_BASE_URL}{path}",
        headers=langfuse_headers(),
        auth=LANGFUSE_AUTH,
        params=params,
        timeout=10.0,
    )


def observation_io_nonempty(payload: Any) -> bool:
    if payload is None or payload == "" or payload == {} or payload == []:
        return False
    if isinstance(payload, dict) and not any(payload.values()):
        return False
    return True


def list_traces(
    *,
    limit: int = 50,
    name: str | None = None,
    session_id: str | None = None,
    user_id: str | None = None,
) -> list[dict]:
    params: dict[str, Any] = {"limit": limit}
    if name:
        params["name"] = name
    if session_id:
        params["sessionId"] = session_id
    if user_id:
        params["userId"] = user_id
    try:
        resp = langfuse_get("/api/public/traces", params=params)
    except httpx.ConnectError:
        pytest.skip(f"Langfuse not reachable at {GATEWAY_BASE_URL}")
    assert resp.status_code == 200, resp.text
    return resp.json().get("data") or []


def trace_detail(trace_id: str) -> dict:
    resp = langfuse_get(f"/api/public/traces/{trace_id}")
    assert resp.status_code == 200, resp.text
    return resp.json()


def trace_observations(detail: dict) -> list[dict]:
    observations = detail.get("observations") or []
    if observations:
        return observations
    trace_id = detail.get("id")
    if not trace_id:
        return []
    resp = langfuse_get(
        "/api/public/observations",
        params={"traceId": trace_id, "limit": 100},
    )
    if resp.status_code != 200:
        return []
    return resp.json().get("data") or []


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
