"""CE-14 opt-in northbound A2A on the sidecar :8000 (real a2a-sdk client, in-process app)."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "images" / "sidecar"))

pytest.importorskip("a2a")
httpx = pytest.importorskip("httpx")

from tests.test_sidecar_inbound import GRAPH, EchoExecutor, _resolver  # noqa: E402
from zelkor_sidecar.a2a_server import mount_a2a  # noqa: E402
from zelkor_sidecar.inbound import Inbound  # noqa: E402
from zelkor_sidecar.store import MemoryStore  # noqa: E402

BASE = "http://agents.test"


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("ZELKOR_A2A_PUBLIC_URL", f"{BASE}/a2a?graph_id={GRAPH}")
    store = MemoryStore()
    inbound = Inbound(store, EchoExecutor(store), graph_id=GRAPH, tenant_resolver=_resolver)
    starlette_app = inbound.app()
    mount_a2a(starlette_app, inbound)
    return starlette_app, store


def _http(app, token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE, headers=headers)


async def _client(app, token):
    from a2a.client import ClientConfig, create_client

    return await create_client(BASE, ClientConfig(streaming=False, httpx_client=_http(app, token)))


def _request(text, context_id=None):
    from a2a.types import Message, Part, Role, SendMessageRequest

    msg = Message(role=Role.ROLE_USER, message_id="m-1", parts=[Part(text=text)])
    if context_id:
        msg.context_id = context_id
    return SendMessageRequest(message=msg)


async def _send(client, req):
    out = []
    async for resp in client.send_message(req):
        out.append(resp)
    return out


def _final(responses):
    for resp in reversed(responses):
        if resp.HasField("task"):
            return resp.task
    raise AssertionError(responses)


def test_card_is_public_and_points_at_graph_route(app):
    starlette_app, _ = app

    async def go():
        async with _http(starlette_app) as http:
            return (await http.get("/.well-known/agent-card.json")).json()

    card = asyncio.run(go())
    assert card["name"] == GRAPH
    assert card["supportedInterfaces"][0]["url"].endswith(f"/a2a?graph_id={GRAPH}")


def test_rpc_requires_jwt(app):
    starlette_app, _ = app

    async def go():
        async with _http(starlette_app) as http:
            return (await http.post("/a2a", json={"jsonrpc": "2.0", "id": 1, "method": "SendMessage",
                                                  "params": {}})).status_code

    assert asyncio.run(go()) == 401


def test_message_round_trip_lands_in_tenant_thread(app):
    starlette_app, store = app

    async def go():
        client = await _client(starlette_app, "tok-a")
        task = _final(await _send(client, _request("hello", context_id="ctx-a")))
        thread = await store.get_thread("tenant-a", GRAPH, "ctx-a")
        msgs = await store.list_messages("tenant-a", GRAPH, "ctx-a")
        return task, thread, msgs

    task, thread, msgs = asyncio.run(go())
    from a2a.types import TaskState

    assert TaskState.Name(task.status.state) == "TASK_STATE_COMPLETED"
    assert any("echo: hello" in p.text for a in task.artifacts for p in a.parts)
    assert thread is not None
    assert [m["type"] for m in msgs] == ["human", "ai"]


def test_context_id_of_another_tenant_is_refused_and_tasks_are_scoped(app):
    starlette_app, store = app

    async def go():
        a = await _client(starlette_app, "tok-a")
        task_a = _final(await _send(a, _request("secret", context_id="ctx-shared")))
        b = await _client(starlette_app, "tok-b")
        task_b = _final(await _send(b, _request("steal", context_id="ctx-shared")))
        from a2a.types import GetTaskRequest

        try:
            await b.get_task(GetTaskRequest(id=task_a.id))
            leaked = True
        except Exception:  # noqa: BLE001 — not found for another tenant
            leaked = False
        b_msgs = await store.list_messages("tenant-b", GRAPH, "ctx-shared")
        return task_b, leaked, b_msgs

    task_b, leaked, b_msgs = asyncio.run(go())
    from a2a.types import TaskState

    assert TaskState.Name(task_b.status.state) == "TASK_STATE_REJECTED"
    assert leaked is False
    assert b_msgs == []
