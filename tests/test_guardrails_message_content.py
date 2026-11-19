"""NeMo answered 500 (KeyError 'content') to an assistant tool_calls message without `content`,
which OpenAI allows; the guardrails image adds `content: null` before NeMo reads the request."""
import asyncio
import json
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "images" / "guardrails"))

import message_content as mc  # noqa: E402

TOOL_TURN = [{"role": "user", "content": "Summarize it."},
             {"role": "assistant", "tool_calls": [{"id": "c1", "type": "function",
                                                   "function": {"name": "f", "arguments": "{}"}}]},
             {"role": "tool", "tool_call_id": "c1", "content": "rows: 3"}]


def test_normalize_adds_null_content_only_where_missing():
    out = json.loads(mc.normalize(json.dumps({"model": "m", "messages": TOOL_TURN}).encode()))
    assert out["messages"][1]["content"] is None
    assert [m["content"] for m in out["messages"]] == ["Summarize it.", None, "rows: 3"]
    assert out["messages"][1]["tool_calls"] == TOOL_TURN[1]["tool_calls"]
    # Unchanged requests and non-chat bodies pass through untouched.
    assert mc.normalize(json.dumps({"messages": [{"role": "user", "content": "hi"}]}).encode()) is None
    assert mc.normalize(b"not json") is None and mc.normalize(b'{"input": "x"}') is None


def _call(path: str, body: bytes):
    seen = {}

    async def inner(scope, receive, send):
        msg = await receive()
        seen["body"], seen["headers"] = msg["body"], dict(scope["headers"])

    scope = {"type": "http", "path": path, "headers": [(b"content-length", str(len(body)).encode())]}
    parts = iter([{"type": "http.request", "body": body[:10], "more_body": True},
                  {"type": "http.request", "body": body[10:], "more_body": False}])

    async def receive():
        return next(parts)

    asyncio.run(mc.AddMissingContent(inner)(scope, receive, None))
    return seen


def test_middleware_rewrites_the_chat_request_and_its_length():
    raw = json.dumps({"messages": TOOL_TURN}).encode()
    seen = _call("/v1/chat/completions", raw)
    assert json.loads(seen["body"])["messages"][1]["content"] is None
    assert seen["headers"][b"content-length"] == str(len(seen["body"])).encode()
    other = _call("/v1/rails/configs", raw)
    assert other["body"] == raw[:10]  # other paths are not read or rewritten


def test_install_adds_the_middleware_once():
    added = []
    api = types.SimpleNamespace(app=types.SimpleNamespace(add_middleware=added.append))
    assert mc.install(api) and mc.install(api)
    assert added == [mc.AddMissingContent]


def test_image_loads_the_patch():
    assert "message_content import install" in (ROOT / "images/guardrails/sitecustomize.py").read_text()
    assert "images/guardrails/message_content.py /app/message_content.py" in (
        ROOT / "images/guardrails/Dockerfile").read_text()
