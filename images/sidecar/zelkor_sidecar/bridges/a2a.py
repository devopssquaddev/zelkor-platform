"""Generic A2A bridge: any runtime serving A2A on 127.0.0.1:8080 needs no Zelkor code.

Mapping: A2A ``context_id`` = Zelkor ``thread_id`` (the runtime keeps its own working
context per context id); A2A task id = the run's runtime id, used for ``CancelTask``.
``a2a-sdk`` 1.x picks A2A 1.0 or the 0.3 compat transport from the runtime's Agent Card.
The answer may arrive as an agent message, a status message, or task artifacts; all are
read and de-duplicated by key. When this sidecar has not seen a thread yet (new pod or
restart) but the thread has history, the stored transcript is sent along so the runtime
can rebuild its context.
"""
from __future__ import annotations

import logging
import re
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional

from ..events import RuntimeEvent, ai_message, text_of
from .base import Bridge

logger = logging.getLogger("zelkor-sidecar")

FAILED_STATES = ("TASK_STATE_FAILED", "TASK_STATE_REJECTED", "TASK_STATE_CANCELED", "TASK_STATE_AUTH_REQUIRED")

# A2A timestamps are RFC 3339. Some servers (fasta2a 2.1.1 InMemoryStorage) send naive
# ``datetime.now().isoformat()``; a2a-sdk's protobuf parser rejects those. Read them as UTC.
_NAIVE_TS = re.compile(rb'("timestamp"\s*:\s*")(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?)(")')


def fix_naive_timestamps(raw: bytes) -> bytes:
    return _NAIVE_TS.sub(rb"\1\2Z\3", raw)


class _LenientTimestampTransport:
    """httpx transport wrapper: adds ``Z`` to zone-less ``timestamp`` values (JSON and SSE)."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    async def handle_async_request(self, request):
        import httpx

        response = await self._inner.handle_async_request(request)
        ctype = response.headers.get("content-type", "")
        if "json" not in ctype and "event-stream" not in ctype:
            return response

        async def lines():
            buf = b""
            async for chunk in response.aiter_raw():
                buf += chunk
                *done, buf = buf.split(b"\n")
                for line in done:
                    yield fix_naive_timestamps(line) + b"\n"
            if buf:
                yield fix_naive_timestamps(buf)
            await response.aclose()

        class _Stream(httpx.AsyncByteStream):
            async def __aiter__(self):
                async for part in lines():
                    yield part

        headers = [(k, v) for k, v in response.headers.raw if k.lower() != b"content-length"]
        return httpx.Response(response.status_code, headers=headers, stream=_Stream(),
                              extensions=response.extensions)

    async def aclose(self) -> None:
        await self._inner.aclose()


def transcript(history: List[Dict[str, Any]]) -> str:
    lines = []
    for msg in history:
        who = {"human": "User", "ai": "Assistant"}.get(str(msg.get("type")), str(msg.get("type")))
        text = text_of(msg).strip()
        if text:
            lines.append(f"{who}: {text}")
    return "\n".join(lines)


def _parts_text(parts: Any) -> str:
    out = []
    for part in parts or []:
        text = getattr(part, "text", "")
        if text:
            out.append(text)
    return "".join(out)


def _state_name(status: Any) -> str:
    from a2a.types import TaskState

    try:
        return TaskState.Name(status.state)
    except Exception:  # noqa: BLE001 — unknown enum value
        return ""


class A2ABridge(Bridge):
    name = "a2a"

    def __init__(self, url: str, *, client_factory: Any = None) -> None:
        self.url = url.rstrip("/")
        self._client: Any = None
        self._client_factory = client_factory
        self._seen: set[str] = set()

    async def _get_client(self):
        if self._client is None:
            if self._client_factory is not None:
                self._client = await self._client_factory(self.url)
            else:
                import httpx
                from a2a.client import ClientConfig, create_client

                http = httpx.AsyncClient(timeout=httpx.Timeout(600.0, connect=5.0),
                                         transport=_LenientTimestampTransport(httpx.AsyncHTTPTransport()))
                self._client = await create_client(self.url, ClientConfig(streaming=True, httpx_client=http))
        return self._client

    async def ready(self) -> bool:
        try:
            await self._get_client()
            return True
        except Exception as exc:  # noqa: BLE001 — not ready until the Agent Card resolves
            logger.debug("A2A runtime not ready: %s", exc)
            self._client = None
            return False

    def build_request(self, ctx: Any, history: List[Dict[str, Any]], new_messages: List[Dict[str, Any]]):
        from a2a.types import Message, Part, Role, SendMessageRequest

        context_id = ctx.runtime_session_id or ctx.thread_id
        parts = []
        prior = history[: max(0, len(history) - len(new_messages))]
        if context_id not in self._seen and prior:
            parts.append(Part(text="Conversation so far:\n" + transcript(prior) + "\n\nNew message:\n"))
        parts.append(Part(text="\n".join(text_of(m) for m in new_messages) or " "))
        message = Message(role=Role.ROLE_USER, message_id=f"zelkor-{uuid.uuid4().hex}",
                          context_id=context_id, parts=parts)
        return SendMessageRequest(message=message), context_id

    async def send_turn(self, ctx, *, history, new_messages) -> AsyncIterator[RuntimeEvent]:
        client = await self._get_client()
        request, context_id = self.build_request(ctx, history, new_messages)
        ctx.runtime_session_id = context_id
        emitted: set[str] = set()

        def message_event(text: str, key: str) -> Optional[RuntimeEvent]:
            if not text or key in emitted:
                return None
            emitted.add(key)
            return RuntimeEvent("message", ai_message(text, f"a2a-{key}"), key=f"a2a-{key}")

        async for resp in client.send_message(request):
            kind = resp.WhichOneof("payload") if hasattr(resp, "WhichOneof") else None
            if kind is None:
                for name in ("message", "task", "status_update", "artifact_update"):
                    if resp.HasField(name):
                        kind = name
                        break
            if kind == "message":
                ev = message_event(_parts_text(resp.message.parts), resp.message.message_id or uuid.uuid4().hex)
                if ev:
                    yield ev
            elif kind == "task":
                task = resp.task
                ctx.runtime_task_id = task.id
                state = _state_name(task.status)
                if state in FAILED_STATES:
                    yield RuntimeEvent("error", {"message": f"A2A task {state}: {_parts_text(task.status.message.parts)}"})
                    return
                for artifact in task.artifacts:
                    ev = message_event(_parts_text(artifact.parts), artifact.artifact_id or task.id)
                    if ev:
                        yield ev
                if task.status.HasField("message"):
                    ev = message_event(_parts_text(task.status.message.parts), task.status.message.message_id or f"{task.id}-status")
                    if ev:
                        yield ev
            elif kind == "status_update":
                upd = resp.status_update
                ctx.runtime_task_id = upd.task_id or getattr(ctx, "runtime_task_id", None)
                state = _state_name(upd.status)
                if state in FAILED_STATES:
                    yield RuntimeEvent("error", {"message": f"A2A task {state}: {_parts_text(upd.status.message.parts)}"})
                    return
                if upd.status.HasField("message") and state != "TASK_STATE_WORKING":
                    ev = message_event(_parts_text(upd.status.message.parts),
                                       upd.status.message.message_id or f"{upd.task_id}-{state}")
                    if ev:
                        yield ev
            elif kind == "artifact_update":
                upd = resp.artifact_update
                ctx.runtime_task_id = upd.task_id or getattr(ctx, "runtime_task_id", None)
                ev = message_event(_parts_text(upd.artifact.parts), upd.artifact.artifact_id or uuid.uuid4().hex)
                if ev:
                    yield ev
        self._seen.add(context_id)

    async def abort(self, ctx) -> None:
        task_id = getattr(ctx, "runtime_task_id", None)
        if not task_id or self._client is None:
            return
        try:
            from a2a.types import CancelTaskRequest

            await self._client.cancel_task(CancelTaskRequest(id=task_id))
        except Exception as exc:  # noqa: BLE001 — best effort on timeout
            logger.warning("A2A cancel failed: %s", type(exc).__name__)

    async def close(self) -> None:
        if self._client is not None and hasattr(self._client, "close"):
            await self._client.close()
