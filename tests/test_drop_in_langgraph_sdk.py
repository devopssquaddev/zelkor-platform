"""Drop-in: stock langgraph_sdk.get_client against the Zelkor Aegra front door."""
from __future__ import annotations

import os
import uuid

import httpx
import pytest
from langgraph_sdk.errors import APIStatusError, NotFoundError

from tests.helpers.langgraph_client import aegra_sdk_client

WORKER_GRAPH_ID = os.environ.get("AEGRA_WORKER_GRAPH_ID", "")


def _http_status(exc: BaseException) -> int | None:
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status
    response = getattr(exc, "response", None)
    return getattr(response, "status_code", None)


def _skip_if_unreachable(exc: BaseException) -> None:
    if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout)):
        pytest.skip(f"Aegra not reachable: {exc}")
    status = _http_status(exc)
    if status is None and "connect" in str(exc).lower():
        pytest.skip(f"Aegra not reachable: {exc}")


async def _search_assistants(client):
    try:
        return await client.assistants.search()
    except Exception as exc:
        _skip_if_unreachable(exc)
        raise


def _thread_ids(hits) -> set[str]:
    rows = hits if isinstance(hits, list) else getattr(hits, "threads", None) or list(hits)
    ids = set()
    for row in rows:
        if isinstance(row, dict):
            ids.add(row["thread_id"])
        else:
            ids.add(row.thread_id)
    return ids


@pytest.mark.asyncio
async def test_sdk_assistants_search_empty_platform_graphs():
    """Stock assistants.search works with empty platform graphs (list may be empty)."""
    client = aegra_sdk_client()
    found = await _search_assistants(client)
    items = found if isinstance(found, list) else getattr(found, "assistants", found)
    assert items is not None
    assert isinstance(items, list) or hasattr(items, "__iter__")


@pytest.mark.asyncio
async def test_sdk_thread_create_get_state():
    """Canonical thread path: create → get → get_state (values present)."""
    client = aegra_sdk_client()
    try:
        thread = await client.threads.create()
        thread_id = thread["thread_id"]
        got = await client.threads.get(thread_id)
        state = await client.threads.get_state(thread_id)
    except Exception as exc:
        _skip_if_unreachable(exc)
        raise
    assert got["thread_id"] == thread_id
    assert "values" in state


@pytest.mark.asyncio
async def test_sdk_thread_search_tenant_isolation():
    """Same-tenant search sees the thread; tenant-b does not (SDK IDOR)."""
    tag = f"drop-in-sdk-{uuid.uuid4().hex[:8]}"
    alice = aegra_sdk_client(tenant_id="tenant-a")
    bob = aegra_sdk_client(tenant_id="tenant-b")
    try:
        thread = await alice.threads.create(metadata={"drop_in": tag})
        thread_id = thread["thread_id"]
        alice_hits = await alice.threads.search(metadata={"drop_in": tag}, limit=50)
        try:
            await bob.threads.get(thread_id)
            bob_got = True
        except (NotFoundError, APIStatusError) as exc:
            bob_got = False
            status = _http_status(exc)
            assert status != 502, exc
            assert status in (None, 403, 404)
        bob_hits = await bob.threads.search(metadata={"drop_in": tag}, limit=50)
    except Exception as exc:
        _skip_if_unreachable(exc)
        raise
    assert thread_id in _thread_ids(alice_hits)
    assert thread_id not in _thread_ids(bob_hits)
    assert bob_got is False


@pytest.mark.asyncio
async def test_sdk_unknown_assistant_is_not_zelkor_502():
    """Unknown assistant_id is an Aegra error, not a Zelkor proxy 502."""
    client = aegra_sdk_client()
    try:
        thread = await client.threads.create()
        await client.runs.wait(
            thread_id=thread["thread_id"],
            assistant_id="missing-drop-in-graph",
            input={"messages": [{"role": "human", "content": "noop"}]},
        )
    except Exception as exc:
        _skip_if_unreachable(exc)
        status = _http_status(exc)
        if status == 502:
            pytest.fail(f"unknown assistant_id must not 502: {exc}")
        if status is not None:
            return
        raise
    pytest.fail("unknown assistant_id should be an Aegra error, not success")


def _require_worker() -> str:
    if not WORKER_GRAPH_ID:
        pytest.skip("AEGRA_WORKER_GRAPH_ID not set (no test-local worker fixture)")
    return WORKER_GRAPH_ID


@pytest.mark.asyncio
async def test_sdk_runs_wait_with_graph_id_header_once():
    """X-Graph-ID is set once on get_client; runs.wait is stock."""
    graph_id = _require_worker()
    client = aegra_sdk_client(graph_id=graph_id)
    try:
        thread = await client.threads.create()
        result = await client.runs.wait(
            thread_id=thread["thread_id"],
            assistant_id=graph_id,
            input={"messages": [{"role": "human", "content": "Say ok"}]},
        )
    except Exception as exc:
        _skip_if_unreachable(exc)
        status = _http_status(exc)
        assert status != 502, exc
        raise
    assert result is not None


@pytest.mark.asyncio
async def test_sdk_runs_stream_with_graph_id_header_once():
    """Stock runs.stream yields at least one chunk; not a Zelkor 502."""
    graph_id = _require_worker()
    client = aegra_sdk_client(graph_id=graph_id)
    chunks = []
    try:
        thread = await client.threads.create()
        async for chunk in client.runs.stream(
            thread["thread_id"],
            graph_id,
            input={"messages": [{"role": "human", "content": "Say ok"}]},
            stream_mode="updates",
        ):
            chunks.append(chunk)
    except Exception as exc:
        _skip_if_unreachable(exc)
        status = _http_status(exc)
        assert status != 502, exc
        raise
    assert chunks, "runs.stream yielded no chunks"
