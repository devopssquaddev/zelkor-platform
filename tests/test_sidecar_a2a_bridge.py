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


def _serve(reply):
    """A real fasta2a server (Pydantic AI) on a free port whose model is ``reply``."""
    from fasta2a.pydantic_ai import agent_to_a2a
    from pydantic_ai import Agent
    from pydantic_ai.models.function import FunctionModel

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
    return url, server, thread


def _prompts(messages):
    return [p.content for m in messages for p in getattr(m, "parts", []) if getattr(p, "part_kind", "") == "user-prompt"]


@pytest.fixture(scope="module")
def a2a_runtime():
    from pydantic_ai.messages import ModelResponse, TextPart

    seen = []

    def reply(messages, _info):
        texts = _prompts(messages)
        seen.append(texts)
        return ModelResponse(parts=[TextPart(f"pong: {texts[-1] if texts else ''}")])

    url, server, thread = _serve(reply)
    yield url, seen
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(scope="module")
def slow_runtime():
    """A turn that is still working when fasta2a answers message/send (a real model or tool call)."""
    from pydantic_ai.messages import ModelResponse, TextPart

    async def reply(messages, _info):
        await asyncio.sleep(1.5)
        texts = _prompts(messages)
        return ModelResponse(parts=[TextPart(f"slow pong: {texts[-1] if texts else ''}")])

    url, server, thread = _serve(reply)
    yield url
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


def test_turn_ends_with_the_runtime_answer_not_its_first_task_snapshot(slow_runtime):
    """fasta2a answers message/send with a submitted/working task. The turn must stay open until the
    task is final: closing it early ends the sidecar run while the runtime still calls its tools
    (409 on /run/active/mcp) and an A2A cancel then finds the task already completed (S-80)."""

    async def go():
        bridge = A2ABridge(slow_runtime)
        msg = {"type": "human", "content": "hello slow", "id": "h1"}
        started = time.monotonic()
        events = await _turn(bridge, _ctx("t-slow"), [msg], [msg])
        await bridge.close()
        return events, time.monotonic() - started

    events, took = asyncio.run(go())
    texts = [e.data["content"] for e in events if e.kind == "message"]
    assert took >= 1.0, f"turn returned after {took:.2f}s, before the runtime answered: {texts}"
    assert texts and texts[-1].endswith("slow pong: hello slow"), texts
    assert "hello slow" not in texts, "the user's own message came back as the agent answer"


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
