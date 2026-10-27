"""Opt-in northbound A2A on :8000 (``sidecar.a2a.enabled``, CE-14).

Same store, executor, governance and trace as Agent Protocol: an A2A turn is a run on
the tenant's thread. ``context_id`` = Zelkor ``thread_id`` (a context id owned by another
tenant is refused); the A2A task store is scoped to the tenant from the verified JWT, so
``tasks/get`` / ``tasks/cancel`` never see another tenant's task. JWT is checked at the
HTTP layer (401, fail closed). A2A 1.0 and 0.3 clients are accepted. Generic A2A clients
do not send ``X-Graph-ID``, so the published URL carries ``?graph_id=`` (Envoy matches it).
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict

logger = logging.getLogger("zelkor-sidecar")

RPC_PATH = "/a2a"


def public_url(graph_id: str) -> str:
    raw = os.getenv("ZELKOR_A2A_PUBLIC_URL", "").strip()
    return raw or f"http://127.0.0.1:8000{RPC_PATH}?graph_id={graph_id}"


def build_card(graph_id: str, url: str):
    from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill

    return AgentCard(
        name=graph_id,
        description=os.getenv("ZELKOR_A2A_DESCRIPTION", f"Zelkor agent {graph_id}"),
        version=os.getenv("ZELKOR_VERSION", "1.0.0"),
        supported_interfaces=[AgentInterface(protocol_binding="JSONRPC", url=url, protocol_version="1.0")],
        capabilities=AgentCapabilities(streaming=True),
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        skills=[AgentSkill(id=graph_id, name=graph_id, description=f"Run {graph_id}", tags=["zelkor"])],
    )


def _headers(context: Any) -> Dict[str, str]:
    raw = (getattr(context, "state", None) or {}).get("headers") or {}
    return {str(k).lower(): str(v) for k, v in raw.items()}


class SidecarA2AExecutor:
    """a2a-sdk AgentExecutor that runs the turn through the sidecar's run path."""

    def __init__(self, inbound: Any) -> None:
        self.inbound = inbound

    async def execute(self, context, event_queue) -> None:
        from a2a.server.tasks import TaskUpdater
        from a2a.types import Part

        headers = _headers(context.call_context)
        tenant = self.inbound.resolve_tenant(headers)  # already checked at HTTP; re-verify
        if context.current_task is None:  # a2a-sdk 1.x: the Task must precede its updates
            from a2a.helpers import new_task
            from a2a.types import TaskState

            await event_queue.enqueue_event(new_task(context.task_id, context.context_id,
                                                     TaskState.TASK_STATE_SUBMITTED,
                                                     history=[context.message] if context.message else None))
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        store, graph = self.inbound.store, self.inbound.graph_id
        thread_id = context.context_id
        if await store.get_thread(tenant, graph, thread_id) is None:
            try:
                await store.create_thread(tenant, graph, {"a2a": True}, thread_id)
            except PermissionError:
                await updater.reject(updater.new_agent_message([Part(text="context id is not available")]))
                return
        await updater.start_work()
        body = {"assistant_id": graph,
                "input": {"messages": [{"role": "human", "content": context.get_user_input()}]}}
        answer, error = "", ""
        async for event, data in self.inbound._run_events(
                tenant, headers.get("authorization", ""), thread_id, body, headers.get("traceparent", "")):
            if event == "updates":
                for msg in (data.get("agent") or {}).get("messages") or []:
                    if msg.get("type") == "ai":
                        from .events import text_of

                        text = text_of(msg)
                        if text:
                            answer = text
                            await updater.add_artifact([Part(text=text)], artifact_id=str(msg.get("id") or ""))
            elif event == "error":
                error = str(data.get("message") or "run failed")
        if error:
            await updater.failed(updater.new_agent_message([Part(text=error[:500])]))
        else:
            await updater.complete(updater.new_agent_message([Part(text=answer)]) if answer else None)

    async def cancel(self, context, event_queue) -> None:
        from a2a.server.tasks import TaskUpdater

        executor = getattr(self.inbound, "executor", None)
        bridge = getattr(executor, "bridge", None)
        slot = getattr(executor, "slot", None)
        if bridge is not None and slot is not None and slot.active is not None:
            await bridge.abort(slot.active)
        await TaskUpdater(event_queue, context.task_id, context.context_id).cancel()


def mount_a2a(app: Any, inbound: Any) -> None:
    """Add the Agent Card route and the authenticated JSON-RPC endpoint to the :8000 app."""
    from a2a.server.request_handlers import DefaultRequestHandler
    from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
    from a2a.server.tasks import InMemoryTaskStore
    from starlette.responses import JSONResponse

    card = build_card(inbound.graph_id, public_url(inbound.graph_id))

    def owner(context) -> str:
        try:
            return inbound.resolve_tenant(_headers(context))
        except PermissionError:
            return "\x00unauthenticated"

    handler = DefaultRequestHandler(agent_executor=SidecarA2AExecutor(inbound),
                                    task_store=InMemoryTaskStore(owner_resolver=owner), agent_card=card)
    rpc_routes = create_jsonrpc_routes(handler, RPC_PATH, enable_v0_3_compat=True)
    for route in rpc_routes:
        inner = route.app

        async def guarded(scope, receive, send, _inner=inner):
            headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
            try:
                inbound.resolve_tenant(headers)
            except PermissionError:
                await JSONResponse({"error": "unauthorized"}, status_code=401)(scope, receive, send)
                return
            await _inner(scope, receive, send)

        route.app = guarded
    app.router.routes.extend(create_agent_card_routes(card) + rpc_routes)
