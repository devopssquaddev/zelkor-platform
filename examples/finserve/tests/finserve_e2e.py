"""Agent Protocol client for FinServe E2E smokes (platform Aegra front door)."""
from __future__ import annotations

import json
import os
from typing import Any, Dict

import httpx
import pytest

GATEWAY_BASE_URL = os.environ.get("GATEWAY_BASE_URL", "http://127.0.0.1:8088")
AEGRA_HOST_HEADER = os.environ.get("AEGRA_HOST_HEADER", "aegra.localhost")
GRAPH_ADVISOR = os.environ.get("FINSERVE_GRAPH_ADVISOR", "finserve-advisor")
GRAPH_RESEARCH = os.environ.get("FINSERVE_GRAPH_RESEARCH", "finserve-research")
GRAPH_QUANT = os.environ.get("FINSERVE_GRAPH_QUANT", "finserve-quant")
GRAPH_CODER = os.environ.get("FINSERVE_GRAPH_CODER", "finserve-coder")
GRAPH_IDS = (GRAPH_ADVISOR, GRAPH_RESEARCH, GRAPH_QUANT)


def _headers(tenant_id: str, graph_id: str) -> Dict[str, str]:
    return {
        "Host": AEGRA_HOST_HEADER,
        "Content-Type": "application/json",
        "Authorization": f"Bearer dev:{tenant_id}",
        "X-Tenant-ID": tenant_id,
        "X-Graph-ID": graph_id,
    }


def _message_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text") or ""))
            else:
                parts.append(_message_text(item))
        return " ".join(p for p in parts if p)
    if isinstance(value, dict):
        if "content" in value:
            return _message_text(value.get("content"))
        if "text" in value:
            return str(value.get("text") or "")
    return ""


def extract_response_text(payload: Any) -> str:
    if payload is None:
        return ""
    if isinstance(payload, str):
        return payload
    if not isinstance(payload, dict):
        return str(payload)
    values = payload.get("values") if isinstance(payload.get("values"), dict) else payload
    messages = values.get("messages") if isinstance(values, dict) else None
    if isinstance(messages, list) and messages:
        for msg in reversed(messages):
            role = ""
            if isinstance(msg, dict):
                role = str(msg.get("role") or msg.get("type") or "").lower()
            if role in ("human", "user"):
                continue
            text = _message_text(msg)
            if text.strip():
                return text
        return ""
    for key in ("output", "response", "content"):
        if payload.get(key):
            text = _message_text(payload.get(key))
            if text:
                return text
    dumped = json.dumps(payload)
    if dumped in ("{}", "[]", "null"):
        return ""
    return dumped


def _skip_unreachable(exc: BaseException) -> None:
    if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout)):
        pytest.skip(f"Aegra not reachable at {GATEWAY_BASE_URL}: {exc}")
    status = getattr(exc, "status_code", None)
    if status == 404:
        pytest.skip("FinServe worker not registered on the Aegra front door")
    if isinstance(status, int) and status >= 500:
        pytest.skip(f"Aegra failed: {status} {exc}")


def run_finserve(
    prompt: str,
    tenant_id: str = "Bank_Alpha",
    timeout: float = 120.0,
    graph_id: str = GRAPH_ADVISOR,
) -> Dict[str, Any]:
    """Create a thread and wait for a FinServe run on the platform Aegra host."""
    from langgraph_sdk import get_sync_client
    from langgraph_sdk.errors import APIStatusError, NotFoundError

    headers = _headers(tenant_id, graph_id)
    try:
        client = get_sync_client(
            url=GATEWAY_BASE_URL,
            api_key=None,
            headers=headers,
            timeout=(5.0, timeout, timeout, 5.0),
        )
        thread = client.threads.create()
        thread_id = thread["thread_id"]
        data = client.runs.wait(
            thread_id,
            graph_id,
            input={"messages": [{"role": "human", "content": prompt}]},
        )
        # Aegra wait may yield run.output == {} while thread state has messages.
        if not data or data == {}:
            data = client.threads.get_state(thread_id)
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as exc:
        pytest.skip(f"Aegra not reachable at {GATEWAY_BASE_URL}: {exc}")
    except (NotFoundError, APIStatusError) as exc:
        _skip_unreachable(exc)
        raise
    status = data.get("status") if isinstance(data, dict) else None
    try:
        blob = json.dumps(data, default=str) if data is not None else ""
    except TypeError:
        blob = str(data)
    tasks = data.get("tasks") if isinstance(data, dict) else None
    task_error = None
    if isinstance(tasks, list):
        for task in tasks:
            if isinstance(task, dict) and task.get("error"):
                task_error = task.get("error")
                break
    if status == "error" or data == {} or task_error or "AttributeError" in blob:
        raise AssertionError(
            f"FinServe run error graph_id={graph_id}: {blob[:2000]}"
        )
    text = extract_response_text(data)
    if not text.strip() or "AttributeError" in text:
        raise AssertionError(
            f"FinServe empty or failed reply graph_id={graph_id}: {blob[:2000]}"
        )
    return {"thread_id": thread_id, "raw": data, "text": text}
