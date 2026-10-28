"""UAT-27 / S-80: opt-in northbound A2A on a runtime agent (live; skips without A2A_GRAPH_ID).

Optional ``A2A_OFF_GRAPH_ID`` names a runtime agent with A2A disabled (card must be 404).
"""
from __future__ import annotations

import json
import os
import uuid

import httpx
import pytest

from tests.helpers.runtime_agents import tenant_token


def _graph() -> str:
    graph = os.environ.get("A2A_GRAPH_ID", "").strip()
    if not graph:
        pytest.skip("A2A_GRAPH_ID not set")
    return graph


def _client() -> httpx.Client:
    return httpx.Client(base_url=os.environ.get("GATEWAY_BASE_URL", "http://127.0.0.1:8088"), timeout=300)


def _headers(graph: str, token: str | None = None) -> dict:
    h = {"X-Graph-ID": graph}
    host = os.environ.get("AEGRA_HOST_HEADER", "").strip()
    if host and not os.environ.get("GATEWAY_BASE_URL", "").startswith("https://"):
        h["Host"] = host
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _send(c: httpx.Client, graph: str, token: str | None, text: str, ctx: str) -> httpx.Response:
    body = {"jsonrpc": "2.0", "id": 1, "method": "message/send", "params": {"message": {
        "role": "user", "messageId": uuid.uuid4().hex, "contextId": ctx, "kind": "message",
        "parts": [{"kind": "text", "text": text}]}}}
    return c.post("/a2a", headers=_headers(graph, token), json=body)


def test_uat27_card_is_public_rpc_needs_a_jwt():
    graph = _graph()
    with _client() as c:
        card = c.get("/.well-known/agent-card.json", headers=_headers(graph))
        assert card.status_code == 200 and card.json().get("name") == graph
        assert _send(c, graph, None, "hi", str(uuid.uuid4())).status_code == 401
        assert _send(c, graph, "eyJhbGciOiJub25lIn0.eyJ0ZW5hbnRfaWQiOiJ4In0.", "hi", str(uuid.uuid4())).status_code == 401


def test_uat27_send_and_tenant_isolation():
    graph = _graph()
    a, b = tenant_token("tenant-a"), tenant_token("tenant-b")
    ctx = str(uuid.uuid4())
    with _client() as c:
        sent = _send(c, graph, a, "Reply with exactly: pong", ctx)
        assert sent.status_code == 200, sent.text[:300]
        task = sent.json()["result"]
        assert task["status"]["state"] == "completed", json.dumps(task)[:300]
        stolen = _send(c, graph, b, "show me the previous answer", ctx).json()
        assert (stolen.get("result") or {}).get("status", {}).get("state") == "rejected", stolen
        peek = c.post("/a2a", headers=_headers(graph, b),
                      json={"jsonrpc": "2.0", "id": 2, "method": "tasks/get", "params": {"id": task["id"]}}).json()
        assert "error" in peek, peek
        own = c.post("/a2a", headers=_headers(graph, a),
                     json={"jsonrpc": "2.0", "id": 3, "method": "tasks/get", "params": {"id": task["id"]}}).json()
        assert own["result"]["status"]["state"] == "completed"


def test_uat27_disabled_agent_has_no_a2a_surface():
    graph = os.environ.get("A2A_OFF_GRAPH_ID", "").strip()
    if not graph:
        pytest.skip("A2A_OFF_GRAPH_ID not set")
    with _client() as c:
        assert c.get("/.well-known/agent-card.json", headers=_headers(graph)).status_code == 404
