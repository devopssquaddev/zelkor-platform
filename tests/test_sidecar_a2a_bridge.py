"""CE-14 generic A2A bridge against a real fasta2a server (Pydantic AI, stub model, no LLM)."""
from __future__ import annotations

import asyncio
import socket
import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "images" / "sidecar"))

pytest.importorskip("a2a")
pytest.importorskip("fasta2a")
pytest.importorskip("pydantic_ai")
uvicorn = pytest.importorskip("uvicorn")

from zelkor_sidecar.bridges.a2a import A2ABridge, transcript  # noqa: E402
from zelkor_sidecar.runs import RunContext  # noqa: E402


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def a2a_runtime():
    from fasta2a.pydantic_ai import agent_to_a2a
    from pydantic_ai import Agent
    from pydantic_ai.messages import ModelResponse, TextPart
    from pydantic_ai.models.function import FunctionModel

    seen = []

    def reply(messages, _info):
        texts = [p.content for m in messages for p in getattr(m, "parts", []) if getattr(p, "part_kind", "") == "user-prompt"]
        seen.append(texts)
        return ModelResponse(parts=[TextPart(f"pong: {texts[-1] if texts else ''}")])

    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    app = agent_to_a2a(Agent(FunctionModel(reply), name="desk"), url=url)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield url, seen
    server.should_exit = True
    thread.join(timeout=5)


def _ctx(thread_id="t-1"):
    return RunContext(tenant_id="tenant-a", bearer="Bearer x", graph_id="desk", thread_id=thread_id, run_id="r-1")


async def _turn(bridge, ctx, history, new):
    return [ev async for ev in bridge.send_turn(ctx, history=history, new_messages=new)]


def test_bridge_round_trip_and_context_id_is_thread_id(a2a_runtime):
    url, _seen = a2a_runtime

    async def go():
        bridge = A2ABridge(url)
        assert await bridge.ready() is True
        ctx = _ctx()
        msg = {"type": "human", "content": "hello", "id": "h1"}
        events = await _turn(bridge, ctx, [msg], [msg])
        await bridge.close()
        return ctx, events

    ctx, events = asyncio.run(go())
    texts = [e.data["content"] for e in events if e.kind == "message"]
    assert texts and texts[-1].endswith("pong: hello")
    assert ctx.runtime_session_id == "t-1"
    assert ctx.runtime_task_id
    assert len({e.key for e in events}) == len(events)


def test_unseen_thread_with_history_sends_transcript(a2a_runtime):
    url, seen = a2a_runtime
    history = [{"type": "human", "content": "first", "id": "h1"},
               {"type": "ai", "content": "answer one", "id": "a1"},
               {"type": "human", "content": "second", "id": "h2"}]

    async def go():
        bridge = A2ABridge(url)
        await _turn(bridge, _ctx("t-restored"), history, history[-1:])
        await bridge.close()

    asyncio.run(go())
    sent = " ".join(seen[-1])
    assert "Conversation so far" in sent and "answer one" in sent and "second" in sent


def test_ready_is_false_when_runtime_is_down():
    async def go():
        bridge = A2ABridge(f"http://127.0.0.1:{_free_port()}")
        return await bridge.ready()

    assert asyncio.run(go()) is False


def test_transcript_format():
    assert transcript([{"type": "human", "content": "a"}, {"type": "ai", "content": [{"type": "text", "text": "b"}]}]) == "User: a\nAssistant: b"
