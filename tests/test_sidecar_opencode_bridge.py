"""CE-14 OpenCode native bridge against a fake ``opencode serve`` (shapes from OpenCode 1.19.4 OpenAPI)."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "images" / "sidecar"))

httpx = pytest.importorskip("httpx")

from zelkor_sidecar.bridges.opencode import OpenCodeBridge, answer_text, error_text  # noqa: E402
from zelkor_sidecar.runs import RunContext  # noqa: E402


class FakeOpenCode:
    def __init__(self, *, error=None, known=()):
        self.sessions = set(known)
        self.prompts = []
        self.aborted = []
        self.error = error

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/global/health":
            return httpx.Response(200, json={"healthy": True, "version": "1.19.4"})
        if path == "/session" and request.method == "POST":
            sid = f"ses_{len(self.sessions) + 1}"
            self.sessions.add(sid)
            return httpx.Response(200, json={"id": sid, "title": json.loads(request.content)["title"]})
        if path.startswith("/session/") and path.endswith("/abort"):
            self.aborted.append(path.split("/")[2])
            return httpx.Response(200, json=True)
        if path.startswith("/session/") and path.endswith("/message"):
            sid = path.split("/")[2]
            texts = [p["text"] for p in json.loads(request.content)["parts"]]
            self.prompts.append((sid, texts))
            info = {"id": "msg_1", "sessionID": sid, "role": "assistant"}
            if self.error:
                info["error"] = self.error
            parts = [{"type": "step-start"}, {"type": "reasoning", "text": "thinking"},
                     {"type": "tool", "tool": "zelkor_postgres__query"},
                     {"type": "text", "text": "the answer"},
                     {"type": "text", "text": " (synthetic)", "synthetic": True}]
            return httpx.Response(200, json={"info": info, "parts": parts})
        if path.startswith("/session/"):
            sid = path.split("/")[2]
            return httpx.Response(200 if sid in self.sessions else 404, json={"id": sid})
        return httpx.Response(404)


def _bridge(fake):
    http = httpx.AsyncClient(base_url="http://oc", transport=httpx.MockTransport(fake))
    return OpenCodeBridge("http://oc", http=http)


def _ctx(session=None):
    return RunContext(tenant_id="tenant-a", bearer="b", graph_id="coder", thread_id="t-1", run_id="r",
                      runtime_session_id=session)


async def _turn(bridge, ctx, history, new):
    return [e async for e in bridge.send_turn(ctx, history=history, new_messages=new)]


H = [{"type": "human", "content": "first", "id": "h1"}, {"type": "ai", "content": "one", "id": "a1"},
     {"type": "human", "content": "second", "id": "h2"}]


def test_new_thread_creates_session_and_returns_visible_text():
    fake = FakeOpenCode()
    ctx = _ctx()
    events = asyncio.run(_turn(_bridge(fake), ctx, H[:1], H[:1]))
    assert ctx.runtime_session_id == "ses_1"
    assert [(e.kind, e.data.get("content")) for e in events] == [("message", "the answer")]
    assert fake.prompts == [("ses_1", ["first"])]


def test_existing_session_is_reused_without_transcript():
    fake = FakeOpenCode(known={"ses_9"})
    ctx = _ctx("ses_9")
    asyncio.run(_turn(_bridge(fake), ctx, H, H[-1:]))
    assert ctx.runtime_session_id == "ses_9"
    assert fake.prompts == [("ses_9", ["second"])]


def test_lost_session_is_recreated_and_seeded_with_transcript():
    fake = FakeOpenCode()
    ctx = _ctx("ses_gone")
    asyncio.run(_turn(_bridge(fake), ctx, H, H[-1:]))
    sid, texts = fake.prompts[0]
    assert sid == ctx.runtime_session_id != "ses_gone"
    assert "Conversation so far" in texts[0] and "one" in texts[0] and texts[1] == "second"


def test_runtime_error_is_an_error_event():
    fake = FakeOpenCode(error={"name": "ProviderAuthError", "data": {"message": "no key"}})
    events = asyncio.run(_turn(_bridge(fake), _ctx(), H[:1], H[:1]))
    assert [e.kind for e in events] == ["error"]
    assert "ProviderAuthError: no key" in events[0].data["message"]


def test_ready_and_abort():
    fake = FakeOpenCode(known={"ses_1"})
    bridge = _bridge(fake)

    async def go():
        assert await bridge.ready() is True
        await bridge.abort(_ctx("ses_1"))

    asyncio.run(go())
    assert fake.aborted == ["ses_1"]


def test_helpers():
    assert answer_text([{"type": "text", "text": "a"}, {"type": "text", "text": "b", "ignored": True}]) == "a"
    assert error_text({}) is None
    assert error_text({"error": "boom"}) == "boom"


class McpFakeOpenCode(FakeOpenCode):
    """OpenCode whose MCP server may be failed (it connected at startup, outside any run)."""

    def __init__(self, status="failed", **kw):
        super().__init__(**kw)
        self.status = status
        self.calls = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/mcp" and request.method == "GET":
            self.calls.append("status")
            return httpx.Response(200, json={"zelkor": {"status": self.status}})
        if path == "/mcp/zelkor/connect" and request.method == "POST":
            self.calls.append("connect")
            self.status = "connected"
            return httpx.Response(200, json=True)
        if path.endswith("/message"):
            self.calls.append(f"message:{self.status}")
        return super().__call__(request)


def test_failed_mcp_server_is_reconnected_inside_the_turn():
    fake = McpFakeOpenCode(status="failed")
    asyncio.run(_turn(_bridge(fake), _ctx(), [H[0]], [H[0]]))
    assert fake.calls == ["status", "connect", "message:connected"]


def test_connected_mcp_server_is_left_alone():
    fake = McpFakeOpenCode(status="connected")
    asyncio.run(_turn(_bridge(fake), _ctx(), [H[0]], [H[0]]))
    assert fake.calls == ["status", "message:connected"]


def test_opencode_without_mcp_status_endpoint_still_runs():
    fake = FakeOpenCode()  # /mcp -> 404
    events = asyncio.run(_turn(_bridge(fake), _ctx(), [H[0]], [H[0]]))
    assert events and events[-1].kind == "message"
