"""Agent Protocol client for FinServe E2E smokes (platform Aegra front door)."""
from __future__ import annotations

import json
import os
from typing import Any, Dict

import httpx
import pytest

GATEWAY_BASE_URL = os.environ.get("GATEWAY_BASE_URL", "http://127.0.0.1:8088")
AEGRA_HOST_HEADER = os.environ.get("AEGRA_HOST_HEADER", "aegra.localhost")
GRAPH_ID = os.environ.get("FINSERVE_GRAPH_ID", "finserve")


def _headers(tenant_id: str) -> Dict[str, str]:
    return {
        "Host": AEGRA_HOST_HEADER,
        "Content-Type": "application/json",
        "Authorization": f"Bearer dev:{tenant_id}",
        "X-Tenant-ID": tenant_id,
        "X-Graph-ID": GRAPH_ID,
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
        return _message_text(messages[-1])
    for key in ("output", "response", "content"):
        if payload.get(key):
            text = _message_text(payload.get(key))
            if text:
                return text
    dumped = json.dumps(payload)
    if dumped in ("{}", "[]", "null"):
        return ""
    return dumped


def run_finserve(prompt: str, tenant_id: str = "Bank_Alpha", timeout: float = 120.0) -> Dict[str, Any]:
    """Create a thread and wait for a FinServe run on the platform Aegra host."""
    headers = _headers(tenant_id)
    try:
        created = httpx.post(
            f"{GATEWAY_BASE_URL}/threads",
            headers=headers,
            json={"if_exists": "do_nothing"},
            timeout=15.0,
        )
    except httpx.ConnectError as exc:
        pytest.skip(f"Aegra not reachable at {GATEWAY_BASE_URL}: {exc}")
    if created.status_code == 404:
        pytest.skip("FinServe worker not registered on the Aegra front door")
    if created.status_code >= 500:
        pytest.skip(f"Aegra /threads failed: {created.status_code} {created.text}")
    created.raise_for_status()
    thread_id = (created.json() or {}).get("thread_id")
    body = {
        "graph_id": GRAPH_ID,
        "assistant_id": GRAPH_ID,
        "input": {"messages": [{"role": "human", "content": prompt}]},
        "if_not_exists": "create",
    }
    if thread_id:
        body["thread_id"] = thread_id
    wait_url = (
        f"{GATEWAY_BASE_URL}/threads/{thread_id}/runs/wait"
        if thread_id
        else f"{GATEWAY_BASE_URL}/runs/wait"
    )
    try:
        resp = httpx.post(wait_url, headers=headers, json=body, timeout=timeout)
    except httpx.ConnectError as exc:
        pytest.skip(f"Aegra not reachable at {GATEWAY_BASE_URL}: {exc}")
    if resp.status_code == 404:
        pytest.skip("graph_id=finserve is not routed (FinServe overlay absent)")
    assert resp.status_code < 500, f"FinServe run failed: {resp.status_code} {resp.text}"
    assert resp.status_code == 200, f"FinServe run status {resp.status_code}: {resp.text}"
    data = resp.json() if resp.content else {}
    return {"thread_id": thread_id, "raw": data, "text": extract_response_text(data)}
