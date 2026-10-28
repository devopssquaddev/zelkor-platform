"""Northbound Agent Protocol on :8000 for non-Aegra runtimes (CE-14).

Covers what ``langgraph_sdk`` and ``zelkor run`` call: assistants search/get, threads
create/get/search/state/history, and runs wait/stream (thread-scoped and stateless).
Auth: tenant JWT (fail closed). Scope: every lookup is (tenant_id, own graph_id); a thread
of another tenant or graph is a 404, never a 403 that would confirm it exists.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, AsyncIterator, Callable, Dict, List, Optional

from .events import normalize_input_messages
from .store import Store, now_iso

logger = logging.getLogger("zelkor-sidecar")

TenantResolver = Callable[[Dict[str, str]], str]


def default_tenant_resolver(headers: Dict[str, str]) -> str:
    from jwt_verifier import resolve_tenant_from_headers  # flat copy from mcp/common

    try:
        return resolve_tenant_from_headers(headers)
    except PermissionError:
        raise
    except Exception as exc:  # noqa: BLE001 — unparseable token / bad alg / JWKS: fail closed as 401, never 500
        raise PermissionError(type(exc).__name__) from exc


def _stream_modes(raw: Any) -> List[str]:
    if raw is None:
        return ["values"]
    if isinstance(raw, str):
        return [raw]
    return [str(m) for m in raw]


def _sse(event: str, data: Any) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n".encode("utf-8")


class Inbound:
    """Holds the dependencies; ``app()`` builds the Starlette application."""

    def __init__(self, store: Store, executor: Any, *, graph_id: str,
                 tenant_resolver: TenantResolver = default_tenant_resolver,
                 ready: Optional[Callable[[], Any]] = None) -> None:
        if not graph_id:
            raise ValueError("graph_id (ZELKOR_GRAPH_ID) is required")
        self.store = store
        self.executor = executor
        self.graph_id = graph_id
        self.resolve_tenant = tenant_resolver
        self._ready = ready

    # -- helpers -----------------------------------------------------------------------

    def assistant(self) -> dict:
        ts = now_iso()
        return {"assistant_id": self.graph_id, "graph_id": self.graph_id, "name": self.graph_id,
                "config": {}, "metadata": {"created_by": "zelkor-sidecar"}, "version": 1,
                "created_at": ts, "updated_at": ts}

    async def state(self, tenant: str, thread_id: str) -> dict:
        messages = await self.store.list_messages(tenant, self.graph_id, thread_id)
        return {"values": {"messages": messages}, "next": [], "tasks": [], "interrupts": [],
                "metadata": {"graph_id": self.graph_id},
                "checkpoint": {"thread_id": thread_id, "checkpoint_ns": "", "checkpoint_id": None},
                "parent_checkpoint": None, "created_at": now_iso()}

    async def thread_view(self, tenant: str, thread: dict) -> dict:
        view = {k: v for k, v in thread.items() if k != "runtime_session_id"}
        view["values"] = (await self.state(tenant, thread["thread_id"]))["values"]
        view.setdefault("interrupts", {})
        return view

    # -- run execution -----------------------------------------------------------------

    async def _run_events(self, tenant: str, bearer: str, thread_id: str, body: dict,
                          traceparent: str) -> AsyncIterator[tuple]:
        """Yield (sse_event, data) for one run; persists messages, events and run status."""
        assistant_id = str(body.get("assistant_id") or self.graph_id)
        if assistant_id != self.graph_id:
            raise LookupError(f"assistant {assistant_id!r} not found")
        new_messages = normalize_input_messages(body.get("input"))
        run = await self.store.create_run(tenant, self.graph_id, thread_id)
        run_id = run["run_id"]
        yield "metadata", {"run_id": run_id, "thread_id": thread_id, "attempt": 1}
        if new_messages:
            await self.store.append_messages(tenant, self.graph_id, thread_id, run_id, new_messages)
        await self.store.set_thread(tenant, self.graph_id, thread_id, status="busy")
        status = "success"
        try:
            async for item in self.executor.execute(
                tenant=tenant, bearer=bearer, graph_id=self.graph_id, thread_id=thread_id,
                run_id=run_id, new_messages=new_messages, traceparent=traceparent,
            ):
                yield item
        except TimeoutError as exc:
            status = "timeout"
            yield "error", {"error": "TimeoutError", "message": str(exc) or "run timed out"}
        except Exception as exc:  # noqa: BLE001 — surfaced to the caller as an error event
            status = "error"
            logger.warning("run failed: %s", type(exc).__name__,
                           extra={"event": "run", "tenant_id": tenant, "run_id": run_id})
            yield "error", {"error": type(exc).__name__, "message": str(exc)[:500]}
        finally:
            await self.store.update_run(run_id, status=status)
            await self.store.set_thread(tenant, self.graph_id, thread_id,
                                        status="idle" if status == "success" else "error")
        values = (await self.state(tenant, thread_id))["values"]
        yield "values", values

    # -- app -----------------------------------------------------------------------------

    def app(self):
        from starlette.applications import Starlette
        from starlette.requests import Request
        from starlette.responses import JSONResponse, StreamingResponse
        from starlette.routing import Route

        inbound = self

        def _headers(request: Request) -> Dict[str, str]:
            return {k.lower(): v for k, v in request.headers.items()}

        def _tenant(request: Request) -> Optional[str]:
            try:
                return inbound.resolve_tenant(_headers(request))
            except PermissionError as exc:
                logger.info("auth denied: %s", type(exc).__name__, extra={"event": "auth"})
                return None

        def _unauth() -> JSONResponse:
            return JSONResponse({"detail": "unauthorized"}, status_code=401)

        def _not_found(what: str = "thread") -> JSONResponse:
            return JSONResponse({"detail": f"{what} not found"}, status_code=404)

        async def _body(request: Request) -> dict:
            raw = await request.body()
            if not raw:
                return {}
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}

        async def health(_request):
            return JSONResponse({"status": "ok"})

        async def ready(_request):
            if inbound._ready is not None:
                ok = await inbound._ready()
                if not ok:
                    return JSONResponse({"status": "runtime not ready"}, status_code=503)
            return JSONResponse({"status": "ready"})

        async def assistants_search(request):
            if _tenant(request) is None:
                return _unauth()
            return JSONResponse([inbound.assistant()])

        async def assistant_get(request):
            if _tenant(request) is None:
                return _unauth()
            if request.path_params["assistant_id"] != inbound.graph_id:
                return _not_found("assistant")
            return JSONResponse(inbound.assistant())

        async def threads_create(request):
            tenant = _tenant(request)
            if tenant is None:
                return _unauth()
            body = await _body(request)
            try:
                thread = await inbound.store.create_thread(
                    tenant, inbound.graph_id, body.get("metadata") or {}, body.get("thread_id"))
            except PermissionError:
                return JSONResponse({"detail": "thread id conflict"}, status_code=409)
            return JSONResponse(await inbound.thread_view(tenant, thread))

        async def threads_search(request):
            tenant = _tenant(request)
            if tenant is None:
                return _unauth()
            body = await _body(request)
            rows = await inbound.store.search_threads(
                tenant, inbound.graph_id, body.get("metadata") or {},
                limit=int(body.get("limit") or 10), offset=int(body.get("offset") or 0))
            return JSONResponse([await inbound.thread_view(tenant, r) for r in rows])

        async def thread_get(request):
            tenant = _tenant(request)
            if tenant is None:
                return _unauth()
            thread = await inbound.store.get_thread(tenant, inbound.graph_id, request.path_params["thread_id"])
            if thread is None:
                return _not_found()
            return JSONResponse(await inbound.thread_view(tenant, thread))

        async def thread_state(request):
            tenant = _tenant(request)
            if tenant is None:
                return _unauth()
            tid = request.path_params["thread_id"]
            if await inbound.store.get_thread(tenant, inbound.graph_id, tid) is None:
                return _not_found()
            return JSONResponse(await inbound.state(tenant, tid))

        async def thread_history(request):
            tenant = _tenant(request)
            if tenant is None:
                return _unauth()
            tid = request.path_params["thread_id"]
            if await inbound.store.get_thread(tenant, inbound.graph_id, tid) is None:
                return _not_found()
            return JSONResponse([await inbound.state(tenant, tid)])

        async def _thread_for_run(request, tenant: str, stateless: bool) -> Optional[str]:
            if stateless:
                thread = await inbound.store.create_thread(tenant, inbound.graph_id, {"stateless": True})
                return thread["thread_id"]
            tid = request.path_params["thread_id"]
            if await inbound.store.get_thread(tenant, inbound.graph_id, tid) is None:
                return None
            return tid

        def _run_handler(*, stream: bool, stateless: bool):
            async def handler(request):
                tenant = _tenant(request)
                if tenant is None:
                    return _unauth()
                body = await _body(request)
                assistant_id = str(body.get("assistant_id") or inbound.graph_id)
                if assistant_id != inbound.graph_id:
                    return _not_found("assistant")
                tid = await _thread_for_run(request, tenant, stateless)
                if tid is None:
                    return _not_found()
                headers = _headers(request)
                bearer = headers.get("authorization", "")
                traceparent = headers.get("traceparent", "")
                events = inbound._run_events(tenant, bearer, tid, body, traceparent)
                if stream:
                    modes = _stream_modes(body.get("stream_mode"))

                    async def gen():
                        async for event, data in events:
                            if event in ("metadata", "error") or event in modes or (
                                event == "custom" and "events" in modes
                            ):
                                yield _sse(event, data)

                    return StreamingResponse(gen(), media_type="text/event-stream",
                                             headers={"Cache-Control": "no-cache"})
                final: Any = None
                error: Optional[dict] = None
                async for event, data in events:
                    if event == "values":
                        final = data
                    elif event == "error":
                        error = data
                if error is not None:
                    return JSONResponse({"__error__": error, **(final or {})}, status_code=500)
                return JSONResponse(final or {})

            return handler

        routes = [
            Route("/health", health, methods=["GET"]),
            Route("/live", health, methods=["GET"]),
            Route("/ok", health, methods=["GET"]),
            Route("/ready", ready, methods=["GET"]),
            Route("/assistants/search", assistants_search, methods=["POST"]),
            Route("/assistants/{assistant_id}", assistant_get, methods=["GET"]),
            Route("/threads", threads_create, methods=["POST"]),
            Route("/threads/search", threads_search, methods=["POST"]),
            Route("/threads/{thread_id}", thread_get, methods=["GET"]),
            Route("/threads/{thread_id}/state", thread_state, methods=["GET"]),
            Route("/threads/{thread_id}/history", thread_history, methods=["GET", "POST"]),
            Route("/threads/{thread_id}/runs/wait", _run_handler(stream=False, stateless=False), methods=["POST"]),
            Route("/threads/{thread_id}/runs/stream", _run_handler(stream=True, stateless=False), methods=["POST"]),
            Route("/runs/wait", _run_handler(stream=False, stateless=True), methods=["POST"]),
            Route("/runs/stream", _run_handler(stream=True, stateless=True), methods=["POST"]),
        ]
        return Starlette(routes=routes)


def graph_id_from_env() -> str:
    return os.getenv("ZELKOR_GRAPH_ID", "").strip()
