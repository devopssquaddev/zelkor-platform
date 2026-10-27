"""Run slot and executor (CE-14, spec P4: one active run per agent replica).

Runtimes take a static base URL (``127.0.0.1:8001/run/active/...``), so the sidecar runs
one turn at a time per pod: the egress proxy resolves ``active`` to the current run's
identity. Further runs wait FIFO. Scale with replicas.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional

from .events import RuntimeEvent, text_of
from .store import Store
from .tracing import Tracing

logger = logging.getLogger("zelkor-sidecar")

_DONE = object()


@dataclass
class RunContext:
    tenant_id: str
    bearer: str
    graph_id: str
    thread_id: str
    run_id: str
    traceparent: str = ""
    runtime: str = ""
    runtime_session_id: Optional[str] = None
    runtime_task_id: Optional[str] = None
    tool_names: List[str] = field(default_factory=list)
    root_span: Any = None
    events: "asyncio.Queue[Any]" = field(default_factory=asyncio.Queue)

    def emit(self, event: str, data: Dict[str, Any], key: str) -> None:
        """Side events from the egress proxy (tool start/end/wait)."""
        self.events.put_nowait(("side", event, data, key))


class RunSlot:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self.active: Optional[RunContext] = None

    async def __aenter__(self) -> "RunSlot":
        await self._lock.acquire()
        return self

    async def __aexit__(self, *_exc) -> None:
        self.active = None
        self._lock.release()


def run_timeout_seconds() -> float:
    raw = os.getenv("ZELKOR_RUN_TIMEOUT", "").strip().lower().rstrip("s")
    try:
        value = float(raw) if raw else 600.0
    except ValueError:
        value = 600.0
    return max(1.0, value)


class RunExecutor:
    def __init__(self, store: Store, bridge: Any, slot: RunSlot, tracing: Tracing, *,
                 runtime: str = "", timeout_s: Optional[float] = None) -> None:
        self.store = store
        self.bridge = bridge
        self.slot = slot
        self.tracing = tracing
        self.runtime = runtime
        self.timeout_s = timeout_s if timeout_s is not None else run_timeout_seconds()

    async def execute(self, *, tenant: str, bearer: str, graph_id: str, thread_id: str,
                      run_id: str, new_messages: List[Dict[str, Any]],
                      traceparent: str = "") -> AsyncIterator[tuple]:
        deadline = time.monotonic() + self.timeout_s
        async with self.slot:
            thread = await self.store.get_thread(tenant, graph_id, thread_id) or {}
            ctx = RunContext(tenant_id=tenant, bearer=bearer, graph_id=graph_id,
                             thread_id=thread_id, run_id=run_id, traceparent=traceparent,
                             runtime=self.runtime,
                             runtime_session_id=thread.get("runtime_session_id"))
            history = await self.store.list_messages(tenant, graph_id, thread_id)
            input_text = text_of(new_messages[-1]) if new_messages else ""
            ctx.root_span = self.tracing.start_root(ctx, input_text=input_text)
            self.slot.active = ctx
            await self.store.update_run(run_id, status="running")
            logger.info("run start", extra={"event": "run", "phase": "start", "tenant_id": tenant,
                                            "run_id": run_id, "graph_id": graph_id})

            async def pump() -> None:
                try:
                    async for ev in self.bridge.send_turn(ctx, history=history, new_messages=new_messages):
                        await ctx.events.put(("bridge", ev))
                except Exception as exc:  # noqa: BLE001 — forwarded as a run error
                    await ctx.events.put(("bridge", RuntimeEvent("error", {"message": f"{type(exc).__name__}: {exc}"})))
                finally:
                    await ctx.events.put(_DONE)

            task = asyncio.create_task(pump())
            output_text = ""
            error = ""
            try:
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError(f"run exceeded {self.timeout_s:.0f}s")
                    try:
                        item = await asyncio.wait_for(ctx.events.get(), timeout=remaining)
                    except asyncio.TimeoutError as exc:
                        raise TimeoutError(f"run exceeded {self.timeout_s:.0f}s") from exc
                    if item is _DONE:
                        break
                    if item[0] == "side":
                        _, event, data, key = item
                        if await self.store.add_event(run_id, key, event, data):
                            yield event, data
                        continue
                    ev: RuntimeEvent = item[1]
                    if ev.kind == "message":
                        msg = dict(ev.data)
                        if not await self.store.add_event(run_id, ev.key, "updates", {"agent": {"messages": [msg]}}):
                            continue
                        await self.store.append_messages(tenant, graph_id, thread_id, run_id, [msg])
                        if msg.get("type") == "ai":
                            output_text = text_of(msg)
                        yield "updates", {"agent": {"messages": [msg]}}
                    elif ev.kind == "error":
                        error = str(ev.data.get("message") or "runtime error")
                        raise RuntimeError(error)
            except TimeoutError as exc:
                error = str(exc)
                await self.bridge.abort(ctx)
                raise
            finally:
                if not task.done():
                    task.cancel()
                if ctx.runtime_session_id and ctx.runtime_session_id != thread.get("runtime_session_id"):
                    await self.store.set_thread(tenant, graph_id, thread_id,
                                                runtime_session_id=ctx.runtime_session_id)
                self.tracing.end_root(ctx.root_span, ctx, output_text=output_text, error=error)
                logger.info("run end", extra={"event": "run", "phase": "end", "tenant_id": tenant,
                                              "run_id": run_id, "status": "error" if error else "ok",
                                              "tool": ",".join(ctx.tool_names)})
