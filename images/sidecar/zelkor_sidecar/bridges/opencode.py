"""OpenCode native bridge: drives ``opencode serve`` on 127.0.0.1:8080 (no A2A).

One OpenCode session per Zelkor thread (session id stored on the thread). A turn is the
documented synchronous ``POST /session/{id}/message``, which returns the assistant message
with its parts once the turn finishes; ``POST /session/{id}/abort`` stops it on timeout.
Tool events come from the sidecar egress (every MCP call passes through it), so the bridge
does not follow ``/event``. A session that no longer exists (runtime restart) is recreated
and seeded with the stored transcript.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from ..events import RuntimeEvent, ai_message, text_of
from .a2a import transcript
from .base import Bridge

logger = logging.getLogger("zelkor-sidecar")


def answer_text(parts: List[Dict[str, Any]]) -> str:
    """Visible answer: text parts that are not synthetic or ignored."""
    return "".join(str(p.get("text", "")) for p in parts or []
                   if p.get("type") == "text" and not p.get("synthetic") and not p.get("ignored"))


def error_text(info: Dict[str, Any]) -> Optional[str]:
    err = info.get("error")
    if not err:
        return None
    if isinstance(err, dict):
        data = err.get("data") if isinstance(err.get("data"), dict) else {}
        return f"{err.get('name', 'OpenCodeError')}: {data.get('message') or err.get('message') or ''}".strip()
    return str(err)


# Name of the MCP server in images/runtime-opencode/opencode.json.
MCP_SERVER = os.getenv("ZELKOR_OPENCODE_MCP_SERVER", "zelkor")


class OpenCodeBridge(Bridge):
    name = "opencode"

    def __init__(self, url: str, *, http: Any = None, timeout_s: float = 600.0) -> None:
        self.url = url.rstrip("/")
        self._http = http
        self._timeout_s = timeout_s

    async def client(self):
        if self._http is None:
            import httpx

            self._http = httpx.AsyncClient(base_url=self.url, timeout=httpx.Timeout(self._timeout_s, connect=5.0))
        return self._http

    async def ready(self) -> bool:
        try:
            r = await (await self.client()).get("/global/health")
            return r.status_code == 200 and bool(r.json().get("healthy"))
        except Exception as exc:  # noqa: BLE001 — not ready until opencode serve answers
            logger.debug("OpenCode not ready: %s", exc)
            return False

    async def _session(self, ctx) -> tuple[str, bool]:
        http = await self.client()
        sid = ctx.runtime_session_id
        if sid:
            r = await http.get(f"/session/{sid}")
            if r.status_code == 200:
                return sid, False
        r = await http.post("/session", json={"title": f"zelkor {ctx.graph_id} {ctx.thread_id}"})
        r.raise_for_status()
        return str(r.json()["id"]), True

    async def _ensure_mcp(self) -> None:
        """Reconnect OpenCode's MCP server inside the run if it is not connected.

        OpenCode connects MCP at startup, when the sidecar has no run and refuses the handshake;
        it then marks the server failed for the life of the process. Reconnecting here happens
        while the run (and its bearer) is active, so the handshake goes through.
        """
        http = await self.client()
        try:
            r = await http.get("/mcp")
            if r.status_code != 200:
                return  # OpenCode without the MCP status API
            status = (r.json().get(MCP_SERVER) or {}).get("status")
            if status == "connected":
                return
            c = await http.post(f"/mcp/{MCP_SERVER}/connect")
            logger.info("OpenCode MCP server reconnected", extra={
                "event": "mcp_session", "status": "ok" if c.status_code < 400 else "error",
                "deny_reason": f"was {status}; connect http {c.status_code}"})
        except Exception as exc:  # noqa: BLE001 — the turn still runs; tools may be missing
            logger.warning("OpenCode MCP status check failed: %s", type(exc).__name__)

    async def send_turn(self, ctx, *, history, new_messages):
        await self._ensure_mcp()
        sid, created = await self._session(ctx)
        ctx.runtime_session_id = sid
        prior = history[: max(0, len(history) - len(new_messages))]
        parts = []
        if created and prior:
            parts.append({"type": "text", "text": "Conversation so far:\n" + transcript(prior) + "\n\nNew message:\n"})
        parts.append({"type": "text", "text": "\n".join(text_of(m) for m in new_messages) or " "})
        r = await (await self.client()).post(f"/session/{sid}/message", json={"parts": parts})
        if r.status_code >= 400:
            yield RuntimeEvent("error", {"message": f"OpenCode HTTP {r.status_code}: {r.text[:300]}"})
            return
        body = r.json()
        info = body.get("info") or {}
        err = error_text(info)
        if err:
            yield RuntimeEvent("error", {"message": err})
            return
        text = answer_text(body.get("parts") or [])
        msg_id = str(info.get("id") or "")
        yield RuntimeEvent("message", ai_message(text, f"opencode-{msg_id}" if msg_id else None),
                           key=f"opencode-{msg_id}" if msg_id else f"opencode-{sid}-{len(history)}")

    async def abort(self, ctx) -> None:
        if not ctx.runtime_session_id or self._http is None:
            return
        try:
            await self._http.post(f"/session/{ctx.runtime_session_id}/abort")
        except Exception as exc:  # noqa: BLE001 — best effort on timeout
            logger.warning("OpenCode abort failed: %s", type(exc).__name__)

    async def close(self) -> None:
        if self._http is not None:
            await self._http.aclose()
