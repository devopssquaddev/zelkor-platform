"""CE-14 zelkor-sidecar :8001 egress proxy + run executor (no cluster)."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "images" / "sidecar"))
sys.path.insert(0, str(ROOT / "images" / "aegra"))  # sandbox_trace (flat copy in the image)

httpx = pytest.importorskip("httpx")
pytest.importorskip("starlette")
from starlette.testclient import TestClient  # noqa: E402

from zelkor_sidecar.egress import (  # noqa: E402
    Egress, EgressConfig, clamp_max_tokens, completion_to_sse, parse_sse, tool_in_scope,
)
from zelkor_sidecar.events import RuntimeEvent, ai_message  # noqa: E402
from zelkor_sidecar.runs import RunContext, RunExecutor, RunSlot  # noqa: E402
from zelkor_sidecar.store import MemoryStore  # noqa: E402
from zelkor_sidecar.tracing import Tracing  # noqa: E402

JWT = "Bearer run-jwt-tenant-a"


class _Stream(httpx.AsyncByteStream):
    """A not-yet-read body, like a real transport returns for SSE."""

    def __init__(self, data: bytes):
        self.data = data

    async def __aiter__(self):
        yield self.data


class Upstream:
    """Records what the sidecar forwards; answers like the MCP / AI gateways."""

    def __init__(self, *, sse=False, tools=("postgres__query", "acme__delete_all")):
        self.requests = []
        self.sse = sse
        self.tools = tools

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path.endswith("/mcp"):
            msg = json.loads(request.content)
            if msg["method"] == "tools/list":
                result = {"tools": [{"name": n} for n in self.tools]}
            else:
                result = {"content": [{"type": "text", "text": json.dumps({"ok": True})}], "isError": False}
            reply = {"jsonrpc": "2.0", "id": msg["id"], "result": result}
            if self.sse:
                return httpx.Response(200, headers={"content-type": "text/event-stream", "mcp-session-id": "s1"},
                                      content=f"event: message\ndata: {json.dumps(reply)}\n\n".encode())
            return httpx.Response(200, json=reply, headers={"mcp-session-id": "s1"})
        body = json.loads(request.content)
        completion = {"id": "c1", "created": 1, "model": body.get("model"),
                      "choices": [{"index": 0, "finish_reason": "tool_calls",
                                   "message": {"role": "assistant", "content": None,
                                               "tool_calls": [{"id": "t1", "type": "function",
                                                               "function": {"name": "x", "arguments": "{}"}}]}}]}
        if body.get("stream"):
            return httpx.Response(200, headers={"content-type": "text/event-stream"},
                                  stream=_Stream(b'data: {"choices": []}\n\ndata: [DONE]\n\n'))
        return httpx.Response(200, json=completion)


def _egress(upstream: Upstream, **cfg):
    slot = RunSlot()
    config = EgressConfig(llm_upstream="http://gw/v1", mcp_upstream="http://mcp/mcp", consumer_key="ck",
                          **cfg)
    http = httpx.AsyncClient(transport=httpx.MockTransport(upstream))
    egress = Egress(slot, Tracing(tracer=None), config, http=http)
    return TestClient(egress.app()), slot


def _activate(slot: RunSlot) -> RunContext:
    ctx = RunContext(tenant_id="tenant-a", bearer=JWT, graph_id="desk", thread_id="t1", run_id="r1")
    slot.active = ctx
    return ctx


def _rpc(method, mid=1, **params):
    return {"jsonrpc": "2.0", "id": mid, "method": method, "params": params}


def test_no_active_run_is_refused():
    client, _ = _egress(Upstream())
    assert client.post("/run/active/mcp", json=_rpc("tools/list")).status_code == 409
    assert client.post("/run/active/v1/chat/completions", json={}).status_code == 409


def test_mcp_bearer_is_the_run_jwt_and_identity_headers_are_stripped():
    up = Upstream()
    client, slot = _egress(up, tool_prefixes=("postgres",))
    _activate(slot)
    client.post("/run/active/mcp", json=_rpc("tools/list"),
                headers={"Authorization": "Bearer runtime-forged", "X-Tenant-ID": "tenant-b",
                         "x-zelkor-langfuse-user-id": "tenant-b"})
    sent = up.requests[-1].headers
    assert sent["authorization"] == JWT
    assert "x-tenant-id" not in sent and "x-zelkor-langfuse-user-id" not in sent


def test_tools_list_is_filtered_to_scope_and_empty_scope_is_none():
    client, slot = _egress(Upstream(), tool_prefixes=("postgres",))
    _activate(slot)
    tools = client.post("/run/active/mcp", json=_rpc("tools/list")).json()["result"]["tools"]
    assert [t["name"] for t in tools] == ["postgres__query"]
    client2, slot2 = _egress(Upstream())
    _activate(slot2)
    assert client2.post("/run/active/mcp", json=_rpc("tools/list")).json()["result"]["tools"] == []


def test_out_of_scope_tools_call_never_reaches_upstream():
    up = Upstream()
    client, slot = _egress(up, tool_prefixes=("postgres",))
    _activate(slot)
    out = client.post("/run/active/mcp", json=_rpc("tools/call", name="acme__delete_all", arguments={})).json()
    assert out["error"]["code"] == -32001
    assert up.requests == []


def test_tools_call_strips_tenant_id_and_emits_tool_events():
    up = Upstream()
    client, slot = _egress(up, tool_allow_all=True)
    ctx = _activate(slot)
    client.post("/run/active/mcp", json=_rpc("tools/call", name="postgres__query",
                                             arguments={"sql": "select 1", "tenant_id": "tenant-b"}))
    forwarded = json.loads(up.requests[-1].content)
    assert forwarded["params"]["arguments"] == {"sql": "select 1"}
    assert ctx.tool_names == ["postgres__query"]
    phases = []
    while not ctx.events.empty():
        _, event, data, _key = ctx.events.get_nowait()
        phases.append((event, data["phase"]))
    assert phases == [("custom", "start"), ("custom", "end")]


def test_sse_mcp_responses_are_filtered_too():
    client, slot = _egress(Upstream(sse=True), tool_prefixes=("postgres",))
    _activate(slot)
    r = client.post("/run/active/mcp", json=_rpc("tools/list"))
    assert r.headers["mcp-session-id"] == "s1"
    (_, data), = parse_sse(r.content)
    assert [t["name"] for t in json.loads(data)["result"]["tools"]] == ["postgres__query"]


def test_llm_gets_consumer_key_cap_and_nemo_stream_rewrite():
    up = Upstream()
    client, slot = _egress(up, max_tokens=256, nemo_tools_no_stream=True)
    _activate(slot)
    r = client.post("/run/active/v1/chat/completions", headers={"Authorization": "Bearer runtime-key"},
                    json={"model": "m", "stream": True, "tools": [{"type": "function"}], "max_tokens": 9999})
    sent = up.requests[-1]
    body = json.loads(sent.content)
    assert sent.headers["authorization"] == "Bearer ck"
    assert body["stream"] is False and body["max_tokens"] == 256
    assert r.headers["content-type"].startswith("text/event-stream")
    chunks = [json.loads(d) for _, d in parse_sse(r.content) if d != "[DONE]"]
    assert chunks[0]["choices"][0]["delta"]["tool_calls"][0]["index"] == 0
    assert r.content.endswith(b"data: [DONE]\n\n")


def test_llm_stream_without_tools_passes_through():
    up = Upstream()
    client, slot = _egress(up, nemo_tools_no_stream=True)
    _activate(slot)
    r = client.post("/run/active/v1/chat/completions", json={"model": "m", "stream": True})
    assert json.loads(up.requests[-1].content)["stream"] is True
    assert b"[DONE]" in r.content


def test_helpers():
    p = {"max_tokens": 10}
    clamp_max_tokens(p, 100)
    assert p["max_tokens"] == 10
    p = {}
    clamp_max_tokens(p, 100)
    assert p["max_tokens"] == 100
    p = {"max_completion_tokens": 500}
    clamp_max_tokens(p, 100)
    assert p == {"max_completion_tokens": 100}
    cfg = EgressConfig(llm_upstream="", mcp_upstream="", tool_prefixes=("pg",))
    assert tool_in_scope("pg__q", cfg) and not tool_in_scope("pgx__q", cfg) and not tool_in_scope("pg", cfg)
    assert completion_to_sse({"choices": []}).endswith(b"data: [DONE]\n\n")


# -- executor ------------------------------------------------------------------------


class FakeBridge:
    def __init__(self, *, error=None, hang=False, session="ses-1"):
        self.error, self.hang, self.session = error, hang, session
        self.seen = []
        self.aborted = False

    async def send_turn(self, ctx, *, history, new_messages):
        self.seen.append([m["content"] for m in history])
        ctx.emit("custom", {"kind": "tool", "name": "postgres__query", "phase": "start"}, "k1")
        if self.hang:
            await asyncio.sleep(10)
        if self.error:
            yield RuntimeEvent("error", {"message": self.error})
            return
        ctx.runtime_session_id = self.session
        yield RuntimeEvent("message", ai_message("done", "m-ai"), key="ai-1")
        yield RuntimeEvent("message", ai_message("done", "m-ai"), key="ai-1")  # replay: stored once

    async def abort(self, ctx):
        self.aborted = True


async def _drive(bridge, timeout_s=5.0):
    store = MemoryStore()
    t = await store.create_thread("tenant-a", "desk")
    await store.append_messages("tenant-a", "desk", t["thread_id"], None,
                                [{"type": "human", "content": "hi", "id": "h1"}])
    run = await store.create_run("tenant-a", "desk", t["thread_id"])
    ex = RunExecutor(store, bridge, RunSlot(), Tracing(tracer=None), timeout_s=timeout_s)
    out = []
    agen = ex.execute(tenant="tenant-a", bearer=JWT, graph_id="desk", thread_id=t["thread_id"],
                      run_id=run["run_id"], new_messages=[{"type": "human", "content": "hi"}])
    async for item in agen:
        out.append(item)
    msgs = await store.list_messages("tenant-a", "desk", t["thread_id"])
    thread = await store.get_thread("tenant-a", "desk", t["thread_id"])
    return {"msgs": msgs, "thread": thread}, t["thread_id"], out


def test_executor_merges_bridge_and_egress_events_and_persists():
    bridge = FakeBridge()
    stored, tid, out = asyncio.run(_drive(bridge))
    assert [e for e, _ in out] == ["custom", "updates"]
    assert bridge.seen == [["hi"]]
    assert [m["content"] for m in stored["msgs"]] == ["hi", "done"]  # replayed message stored once
    assert stored["thread"]["runtime_session_id"] == "ses-1"
    assert out[1][1]["agent"]["messages"][0]["content"] == "done"


def test_executor_error_and_timeout():
    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(_drive(FakeBridge(error="boom")))
    bridge = FakeBridge(hang=True)
    with pytest.raises(TimeoutError):
        asyncio.run(_drive(bridge, timeout_s=1.0))
    assert bridge.aborted is True


def test_run_slot_is_one_at_a_time():
    async def go():
        slot = RunSlot()
        order = []

        async def run(tag):
            async with slot:
                order.append(f"{tag}-in")
                await asyncio.sleep(0.05)
                order.append(f"{tag}-out")

        await asyncio.gather(run("a"), run("b"))
        return order

    assert asyncio.run(go()) == ["a-in", "a-out", "b-in", "b-out"]


def test_tool_messages_lose_non_standard_name_field():
    """CrewAI sends {"role": "tool", "name": ...}; strict OpenAI-schema upstreams answer 422."""
    up = Upstream()
    client, slot = _egress(up)
    _activate(slot)
    client.post("/run/active/v1/chat/completions", json={"model": "m", "messages": [
        {"role": "user", "content": "q", "name": "alice"},
        {"role": "assistant", "content": None, "tool_calls": [{"id": "c1", "type": "function",
                                                               "function": {"name": "t", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "c1", "name": "t", "content": "ok"},
    ]})
    sent = json.loads(up.requests[-1].content)["messages"]
    assert "name" not in sent[2]
    assert sent[0]["name"] == "alice"  # only tool messages are rewritten


def test_child_spans_carry_trace_identity():
    """Langfuse v4 events mode groups by per-span identity; children must carry it too."""
    pytest.importorskip("opentelemetry.sdk")
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracing = Tracing(tracer=provider.get_tracer("t"))
    ctx = RunContext(tenant_id="tenant-a", bearer=JWT, graph_id="desk", thread_id="t1", run_id="r1")
    ctx.root_span = tracing.start_root(ctx, input_text="hi")
    with tracing.child(ctx, "sandbox__execute_python", observation_type="tool"):
        pass
    tracing.end_root(ctx.root_span, ctx)
    spans = {s.name: s for s in exporter.get_finished_spans()}
    child = spans["sandbox__execute_python"]
    assert child.attributes["langfuse.trace.name"] == "desk"
    assert child.attributes["langfuse.session.id"] == "t1"
    assert child.attributes["langfuse.user.id"] == "tenant-a"
    assert child.parent.span_id == spans["desk"].context.span_id
