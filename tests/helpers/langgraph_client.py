"""Stock langgraph_sdk client pointed at the Zelkor Aegra front door.

Platform-only tests use async ``get_client``. Worker-routed runs (``graph_id`` /
``X-Graph-ID``) use ``get_sync_client`` — same pattern as FinServe E2E — wrapped
for ``@pytest.mark.asyncio`` via ``asyncio.to_thread``.
"""
from __future__ import annotations

import asyncio
import os
from typing import Any

from langgraph_sdk import get_client, get_sync_client

_DEFAULT_TENANT = "tenant-a"


def _gateway_url() -> str:
    return os.environ.get("GATEWAY_BASE_URL", "http://127.0.0.1:8088")


def _request_headers(*, tenant_id: str, graph_id: str | None = None) -> dict[str, str]:
    token = os.environ.get("AEGRA_AUTH_TOKEN") if tenant_id == _DEFAULT_TENANT else None
    headers = {
        "Authorization": f"Bearer {token or f'dev:{tenant_id}'}",
        "Host": os.environ.get("AGENTS_HOST_HEADER")
        or os.environ.get("AEGRA_HOST_HEADER", "aegra.localhost"),
        "X-Tenant-ID": tenant_id,
    }
    if graph_id:
        headers["X-Graph-ID"] = graph_id
    return headers


class _AsyncSyncThreads:
    def __init__(self, sync_threads: Any) -> None:
        self._sync = sync_threads

    async def create(self, *args, **kwargs):
        return await asyncio.to_thread(self._sync.create, *args, **kwargs)

    async def get(self, *args, **kwargs):
        return await asyncio.to_thread(self._sync.get, *args, **kwargs)

    async def get_state(self, *args, **kwargs):
        return await asyncio.to_thread(self._sync.get_state, *args, **kwargs)

    async def search(self, *args, **kwargs):
        return await asyncio.to_thread(self._sync.search, *args, **kwargs)


class _AsyncSyncRuns:
    def __init__(self, sync_runs: Any) -> None:
        self._sync = sync_runs

    async def wait(self, thread_id, assistant_id, **kwargs):
        return await asyncio.to_thread(
            self._sync.wait,
            thread_id,
            assistant_id,
            **kwargs,
        )

    def stream(self, thread_id, assistant_id, **kwargs):
        return _AsyncSyncRunStream(self._sync.stream, thread_id, assistant_id, kwargs)


class _AsyncSyncRunStream:
    def __init__(self, stream_fn, thread_id, assistant_id, kwargs: dict) -> None:
        self._stream_fn = stream_fn
        self._thread_id = thread_id
        self._assistant_id = assistant_id
        self._kwargs = kwargs
        self._chunks: list[Any] | None = None
        self._index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._chunks is None:
            self._chunks = await asyncio.to_thread(
                lambda: list(
                    self._stream_fn(self._thread_id, self._assistant_id, **self._kwargs)
                )
            )
        if self._index >= len(self._chunks):
            raise StopAsyncIteration
        chunk = self._chunks[self._index]
        self._index += 1
        return chunk


class _AsyncSyncAssistants:
    def __init__(self, sync_assistants: Any) -> None:
        self._sync = sync_assistants

    async def search(self, *args, **kwargs):
        return await asyncio.to_thread(self._sync.search, *args, **kwargs)


class _AsyncSyncLangGraphClient:
    """Async facade over sync langgraph_sdk client for worker HTTPRoute routing."""

    def __init__(self, sync_client: Any) -> None:
        self._sync = sync_client
        self.threads = _AsyncSyncThreads(sync_client.threads)
        self.runs = _AsyncSyncRuns(sync_client.runs)
        self.assistants = _AsyncSyncAssistants(sync_client.assistants)


def aegra_sdk_client(*, tenant_id: str = _DEFAULT_TENANT, graph_id: str | None = None) -> Any:
    headers = _request_headers(tenant_id=tenant_id, graph_id=graph_id)
    if graph_id:
        sync_client = get_sync_client(
            url=_gateway_url(),
            api_key=None,
            headers=headers,
            timeout=(5.0, 180.0, 180.0, 5.0),
        )
        return _AsyncSyncLangGraphClient(sync_client)
    return get_client(
        url=_gateway_url(),
        api_key=None,
        headers=headers,
    )
