"""CE-14 zelkor-sidecar northbound Agent Protocol + store (no cluster, no Postgres)."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "images" / "sidecar"))

pytest.importorskip("starlette")
from starlette.testclient import TestClient  # noqa: E402

from zelkor_sidecar.events import ai_message, normalize_input_messages  # noqa: E402
from zelkor_sidecar.inbound import Inbound  # noqa: E402
from zelkor_sidecar.store import MemoryStore  # noqa: E402

GRAPH = "desk"
TOKENS = {"Bearer tok-a": "tenant-a", "Bearer tok-b": "tenant-b"}


def _resolver(headers):
    tenant = TOKENS.get(headers.get("authorization", ""))
    if tenant is None:
        raise PermissionError("invalid bearer")
    return tenant


class EchoExecutor:
    """Stands in for runs.RunExecutor: replies with the last human text."""

    def __init__(self, store, *, fail: Exception | None = None):
        self.store = store
        self.fail = fail
        self.calls = []

    async def execute(self, *, tenant, bearer, graph_id, thread_id, run_id, new_messages, traceparent):
        self.calls.append({"tenant": tenant, "bearer": bearer, "thread_id": thread_id, "traceparent": traceparent})
        if self.fail:
            raise self.fail
        yield "custom", {"kind": "tool", "name": "postgres__query", "phase": "start"}
        reply = ai_message(f"echo: {new_messages[-1]['content'] if new_messages else ''}")
        await self.store.append_messages(tenant, graph_id, thread_id, run_id, [reply])
        yield "updates", {"agent": {"messages": [reply]}}


def _client(executor_factory=EchoExecutor):
    store = MemoryStore()
    executor = executor_factory(store)
    app = Inbound(store, executor, graph_id=GRAPH, tenant_resolver=_resolver).app()
    return TestClient(app), store, executor


A = {"Authorization": "Bearer tok-a"}
B = {"Authorization": "Bearer tok-b"}
RUN = {"assistant_id": GRAPH, "input": {"messages": [{"role": "human", "content": "hi"}]}}


def test_unauthenticated_requests_are_401_everywhere():
    client, _, _ = _client()
    for method, path in [("post", "/threads"), ("post", "/threads/search"), ("post", "/assistants/search"),
                         ("get", "/threads/x"), ("post", "/runs/wait")]:
        assert client.request(method.upper(), path).status_code == 401, path
        assert client.request(method.upper(), path, headers={"Authorization": "Bearer nope"}).status_code == 401


def test_health_probes_need_no_auth():
    client, _, _ = _client()
    for path in ("/health", "/live", "/ready"):
        assert client.get(path).status_code == 200


def test_assistants_search_and_get():
    client, _, _ = _client()
    found = client.post("/assistants/search", json={}, headers=A).json()
    assert [a["assistant_id"] for a in found] == [GRAPH]
    assert client.get(f"/assistants/{GRAPH}", headers=A).status_code == 200
    assert client.get("/assistants/other", headers=A).status_code == 404


def test_thread_create_get_state():
    client, _, _ = _client()
    thread = client.post("/threads", json={"metadata": {"k": "v"}}, headers=A).json()
    tid = thread["thread_id"]
    got = client.get(f"/threads/{tid}", headers=A).json()
    assert got["thread_id"] == tid and got["metadata"] == {"k": "v"}
    assert "runtime_session_id" not in got
    state = client.get(f"/threads/{tid}/state", headers=A).json()
    assert state["values"] == {"messages": []}


def test_tenant_isolation_on_every_thread_route():
    """P1: tenant-b cannot read, search, inspect or run tenant-a's thread; all look like 404."""
    client, _, executor = _client()
    tid = client.post("/threads", json={"metadata": {"tag": "iso"}}, headers=A).json()["thread_id"]
    assert client.get(f"/threads/{tid}", headers=B).status_code == 404
    assert client.get(f"/threads/{tid}/state", headers=B).status_code == 404
    assert client.post(f"/threads/{tid}/history", json={}, headers=B).status_code == 404
    assert client.post(f"/threads/{tid}/runs/wait", json=RUN, headers=B).status_code == 404
    assert client.post(f"/threads/{tid}/runs/stream", json=RUN, headers=B).status_code == 404
    assert client.post("/threads/search", json={"metadata": {"tag": "iso"}}, headers=B).json() == []
    assert [t["thread_id"] for t in client.post("/threads/search", json={"metadata": {"tag": "iso"}},
                                                  headers=A).json()] == [tid]
    # Reusing another tenant's thread id is a conflict, not a takeover.
    assert client.post("/threads", json={"thread_id": tid}, headers=B).status_code == 409
    assert executor.calls == []


def test_unknown_assistant_is_404_not_502():
    client, _, _ = _client()
    tid = client.post("/threads", json={}, headers=A).json()["thread_id"]
    r = client.post(f"/threads/{tid}/runs/wait", json={**RUN, "assistant_id": "missing"}, headers=A)
    assert r.status_code == 404


def test_runs_wait_returns_final_values_and_persists_messages():
    client, store, executor = _client()
    tid = client.post("/threads", json={}, headers={**A, "traceparent": "00-abc-def-01"}).json()["thread_id"]
    out = client.post(f"/threads/{tid}/runs/wait", json=RUN,
                      headers={**A, "traceparent": "00-" + "1" * 32 + "-" + "2" * 16 + "-01"}).json()
    msgs = out["messages"]
    assert [m["type"] for m in msgs] == ["human", "ai"]
    assert msgs[1]["content"] == "echo: hi"
    assert executor.calls[0]["bearer"] == "Bearer tok-a"
    assert executor.calls[0]["traceparent"].startswith("00-111")
    state = client.get(f"/threads/{tid}/state", headers=A).json()
    assert len(state["values"]["messages"]) == 2


def test_runs_stream_sse_events_follow_stream_mode():
    client, _, _ = _client()
    tid = client.post("/threads", json={}, headers=A).json()["thread_id"]
    with client.stream("POST", f"/threads/{tid}/runs/stream",
                       json={**RUN, "stream_mode": ["events", "updates"]}, headers=A) as r:
        assert r.status_code == 200
        body = r.read().decode()
    events = [line.split(": ", 1)[1] for line in body.splitlines() if line.startswith("event: ")]
    assert events[0] == "metadata"
    assert "custom" in events and "updates" in events
    assert "values" not in events  # not requested
    data = [json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: ")]
    assert data[0]["thread_id"] == tid


def test_stateless_run_creates_a_thread():
    client, _, _ = _client()
    out = client.post("/runs/wait", json=RUN, headers=A).json()
    assert out["messages"][-1]["content"] == "echo: hi"


def test_executor_failure_is_an_error_event_and_run_status():
    client, store, _ = _client(lambda s: EchoExecutor(s, fail=RuntimeError("runtime down")))
    tid = client.post("/threads", json={}, headers=A).json()["thread_id"]
    r = client.post(f"/threads/{tid}/runs/wait", json=RUN, headers=A)
    assert r.status_code == 500
    assert r.json()["__error__"]["message"] == "runtime down"
    assert client.get(f"/threads/{tid}", headers=A).json()["status"] == "error"


def test_normalize_input_messages():
    msgs = normalize_input_messages({"messages": [{"role": "user", "content": "a"}, "b",
                                                  {"type": "assistant", "content": "c"}]})
    assert [m["type"] for m in msgs] == ["human", "human", "ai"]
    assert all(m["id"] for m in msgs)


def test_store_events_are_idempotent_per_key():
    async def go():
        store = MemoryStore()
        t = await store.create_thread("tenant-a", GRAPH)
        run = await store.create_run("tenant-a", GRAPH, t["thread_id"])
        assert await store.add_event(run["run_id"], "evt-1", "custom", {"x": 1}) is True
        assert await store.add_event(run["run_id"], "evt-1", "custom", {"x": 1}) is False
        assert await store.add_event(run["run_id"], "evt-2", "custom", {"x": 2}) is True
        seqs = [e["seq"] for e in await store.list_events(run["run_id"])]
        assert seqs == sorted(seqs) and len(seqs) == 2
        assert await store.get_run("tenant-b", GRAPH, run["run_id"]) is None

    asyncio.run(go())


def test_migrations_are_numbered_and_unique():
    from zelkor_sidecar.migrate import available_migrations, pending

    avail = available_migrations()
    assert [v for v, _ in avail] == sorted(v for v, _ in avail)
    assert avail[0][0] == 1
    assert pending({1}, avail) == avail[1:]
    sql = avail[0][1].read_text()
    for table in ("zelkor_threads", "zelkor_runs", "zelkor_messages", "zelkor_run_events"):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql
    assert "UNIQUE (run_id, event_key)" in sql
