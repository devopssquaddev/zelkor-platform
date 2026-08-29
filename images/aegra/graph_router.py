"""Aegra front-door graph_id router.

Local/eval graphs in aegra.json are served in-process. Independently released
workers are ClusterIP Aegra pods listed in AEGRA_WORKERS (JSON list of
{graphId, url}). Agent Protocol requests whose graph_id / assistant_id match a
worker are reverse-proxied.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Dict, Optional
from urllib.parse import parse_qs

try:
    import httpx
except ImportError:
    httpx = None

try:
    from starlette.responses import JSONResponse
    from starlette.types import ASGIApp, Receive, Scope, Send
except ImportError:
    JSONResponse = None  # type: ignore[misc, assignment]
    ASGIApp = object  # type: ignore[misc, assignment]
    Receive = object  # type: ignore[misc, assignment]
    Scope = dict  # type: ignore[misc, assignment]
    Send = object  # type: ignore[misc, assignment]

logger = logging.getLogger("zelkor-graph-router")

try:
    from aegra_api.main import app as _inner_app
except ImportError:
    _inner_app = None

HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}

LOCAL_PREFIXES = ("/health", "/ready", "/docs", "/openapi.json")


def load_workers(raw: Optional[str] = None) -> Dict[str, str]:
    text = raw if raw is not None else os.getenv("AEGRA_WORKERS", "[]")
    data = json.loads(text or "[]")
    catalog: Dict[str, str] = {}
    if not isinstance(data, list):
        raise ValueError("AEGRA_WORKERS must be a JSON list of {graphId, url}")
    for item in data:
        if not isinstance(item, dict):
            raise ValueError("worker entries must be objects")
        graph_id = (item.get("graphId") or item.get("graph_id") or "").strip()
        url = (item.get("url") or "").rstrip("/")
        if not graph_id or not url:
            raise ValueError("worker requires graphId and url")
        catalog[graph_id] = url
    return catalog


WORKERS = load_workers()


def extract_graph_id(body: object, query: dict) -> Optional[str]:
    for key in ("graph_id", "graphId", "assistant_id", "assistantId"):
        value = query.get(key)
        if isinstance(value, list):
            value = value[0] if value else None
        if value:
            return str(value)
    if isinstance(body, dict):
        for key in ("graph_id", "graphId", "assistant_id", "assistantId"):
            value = body.get(key)
            if value:
                return str(value)
        config = body.get("config") if isinstance(body.get("config"), dict) else {}
        configurable = config.get("configurable") if isinstance(config.get("configurable"), dict) else {}
        for key in ("graph_id", "graphId"):
            value = configurable.get(key)
            if value:
                return str(value)
    return None


def _header_map(scope: Scope) -> Dict[str, str]:
    return {k.decode("latin-1"): v.decode("latin-1") for k, v in scope.get("headers") or []}


async def _buffer_body(receive: Receive) -> bytes:
    chunks = []
    more = True
    while more:
        message = await receive()
        if message["type"] == "http.request":
            chunks.append(message.get("body") or b"")
            more = bool(message.get("more_body"))
        else:
            more = False
    return b"".join(chunks)


def _replay(body: bytes) -> Receive:
    sent = False

    async def receive() -> dict:
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    return receive


async def proxy_to_worker(scope: Scope, body: bytes, base_url: str, send: Send) -> None:
    if httpx is None:
        raise RuntimeError("httpx is required to proxy graph_id to workers")
    path = scope.get("path") or ""
    query = (scope.get("query_string") or b"").decode("latin-1")
    url = f"{base_url}{path}"
    if query:
        url = f"{url}?{query}"
    headers = {
        k: v
        for k, v in _header_map(scope).items()
        if k.lower() not in HOP_BY_HOP
    }
    method = scope.get("method") or "GET"
    if httpx is None:
        raise RuntimeError("httpx is required to proxy graph_id to workers")
    timeout = httpx.Timeout(120.0, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        req = client.build_request(method, url, headers=headers, content=body or None)
        resp = await client.send(req, stream=True)
        out_headers = [
            (k.encode("latin-1"), v.encode("latin-1"))
            for k, v in resp.headers.items()
            if k.lower() not in HOP_BY_HOP
        ]
        await send(
            {
                "type": "http.response.start",
                "status": resp.status_code,
                "headers": out_headers,
            }
        )
        async for chunk in resp.aiter_bytes():
            await send({"type": "http.response.body", "body": chunk, "more_body": True})
        await send({"type": "http.response.body", "body": b"", "more_body": False})
        await resp.aclose()


class GraphRouter:
    def __init__(self, inner: ASGIApp, workers: Optional[Dict[str, str]] = None):
        self.inner = inner
        self.workers = workers if workers is not None else WORKERS

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self.workers:
            await self.inner(scope, receive, send)
            return
        path = scope.get("path") or ""
        if any(path == p or path.startswith(p + "/") for p in LOCAL_PREFIXES):
            await self.inner(scope, receive, send)
            return

        body = await _buffer_body(receive)
        body_obj = None
        if body:
            try:
                body_obj = json.loads(body.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                body_obj = None
        query = parse_qs((scope.get("query_string") or b"").decode("latin-1"))
        graph_id = extract_graph_id(body_obj, query)
        if graph_id and graph_id in self.workers:
            await proxy_to_worker(scope, body, self.workers[graph_id], send)
            return
        await self.inner(scope, _replay(body), send)


def build_app() -> ASGIApp:
    if _inner_app is None:
        async def _missing(scope, receive, send):
            response = JSONResponse({"error": "aegra_api not installed"}, status_code=500)
            await response(scope, receive, send)

        return _missing
    return GraphRouter(_inner_app)


app = build_app()
