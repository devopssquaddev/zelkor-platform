"""Agent Protocol client for legal-redline live tests."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest

GATEWAY_BASE_URL = os.environ.get("GATEWAY_BASE_URL", "http://127.0.0.1:8088")
AEGRA_HOST_HEADER = os.environ.get("AGENTS_HOST_HEADER") or os.environ.get(
    "AEGRA_HOST_HEADER", "agents.localhost"
)
GRAPH_ID = os.environ.get("LEGAL_REDLINE_GRAPH_ID", "legal-redline")
TENANT_A = os.environ.get("LEGAL_REDLINE_TENANT_A", "harborline-freight")
TENANT_B = os.environ.get("LEGAL_REDLINE_TENANT_B", "brightpath-clinics")
RULE_A = "hlf-liability-cap-stays"
RULE_B = "bpc-liability-cap-network"

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _bearer(tenant_id: str) -> str:
    from tests.helpers.tokens import bearer_for, test_tokens

    try:
        return bearer_for(tenant_id)
    except KeyError:
        if not test_tokens():
            pytest.skip("ZELKOR_TEST_TOKENS not set")
        pytest.skip(f"No bearer for tenant {tenant_id!r}")


def _headers(tenant_id: str) -> dict[str, str]:
    return {
        "Host": AEGRA_HOST_HEADER,
        "Content-Type": "application/json",
        "Authorization": _bearer(tenant_id),
        "X-Graph-ID": GRAPH_ID,
    }


def _message_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(_message_text(item) for item in value if _message_text(item))
    if isinstance(value, dict):
        if "content" in value:
            return _message_text(value.get("content"))
        if "text" in value:
            return str(value.get("text") or "")
    return ""


def extract_assistant_json(payload: Any) -> dict[str, Any]:
    values = payload.get("values") if isinstance(payload, dict) and isinstance(payload.get("values"), dict) else payload
    if not isinstance(values, dict):
        return {}
    if isinstance(values.get("suggestion"), dict):
        return values["suggestion"]
    messages = values.get("messages") or []
    if isinstance(messages, list):
        for msg in reversed(messages):
            text = _message_text(msg)
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                try:
                    parsed = json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict) and parsed.get("decision"):
                    return parsed
    return {}


def run_review(
    *,
    clause_id: str,
    proposed: str,
    tenant_id: str = TENANT_A,
    counterparty: str = "North Pier Logistics",
    thread_id: str | None = None,
    extra: dict[str, Any] | None = None,
    timeout: float = 180.0,
) -> dict[str, Any]:
    from langgraph_sdk import get_sync_client
    from langgraph_sdk.errors import APIStatusError, NotFoundError

    headers = _headers(tenant_id)
    try:
        client = get_sync_client(
            url=GATEWAY_BASE_URL,
            api_key=None,
            headers=headers,
            timeout=(5.0, timeout, timeout, 5.0),
        )
        if thread_id:
            tid = thread_id
            payload = extra or {"messages": [{"role": "human", "content": proposed}]}
        else:
            thread = client.threads.create()
            tid = thread["thread_id"]
            payload = {
                "messages": [{"role": "human", "content": "Review this counterparty edit."}],
                "clause_id": clause_id,
                "object_key": "contracts/msa.txt",
                "proposed": proposed,
                "counterparty": counterparty,
            }
            if extra:
                payload.update(extra)
        data = client.runs.wait(tid, GRAPH_ID, input=payload)
        if not data or data == {}:
            data = client.threads.get_state(tid)
        state = client.threads.get_state(tid)
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as exc:
        pytest.skip(f"Aegra not reachable at {GATEWAY_BASE_URL}: {exc}")
    except (NotFoundError, APIStatusError) as exc:
        status = getattr(exc, "status_code", None)
        if status in (404, 401, 403):
            pytest.skip(f"legal-redline not reachable: {status}")
        if isinstance(status, int) and status >= 500:
            pytest.skip(f"Aegra failed: {status}")
        raise
    suggestion = extract_assistant_json(data) or extract_assistant_json(state)
    values = state.get("values") if isinstance(state, dict) else {}
    sandbox = values.get("sandbox") if isinstance(values, dict) else {}
    return {
        "thread_id": tid,
        "raw": data,
        "state": state,
        "suggestion": suggestion,
        "sandbox": sandbox if isinstance(sandbox, dict) else {},
    }
