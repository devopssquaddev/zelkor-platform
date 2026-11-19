"""Give every chat message a ``content`` key before NeMo reads the request.

OpenAI lets an assistant message that carries ``tool_calls`` omit ``content``. NeMo 0.24.1 builds
its history cache key with ``msg["content"]`` (``rails/llm/utils.py``), so such a request raised
KeyError and the server answered 500. The OpenAI SDKs send ``"content": null``, which NeMo
accepts; this middleware makes a request without the key look the same.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

_log = logging.getLogger("zelkor-nemo")
_PATH = "/v1/chat/completions"
_PATCHED = "_zelkor_message_content"


def normalize(raw: bytes) -> Optional[bytes]:
    """The request body with ``content: null`` added where a message has no ``content``; None
    when nothing changed (or the body is not a JSON chat request)."""
    try:
        body = json.loads(raw.decode("utf-8") or "{}")
    except (UnicodeError, json.JSONDecodeError):
        return None
    messages = body.get("messages") if isinstance(body, dict) else None
    if not isinstance(messages, list):
        return None
    added = 0
    for msg in messages:
        if isinstance(msg, dict) and "content" not in msg:
            msg["content"] = None
            added += 1
    if not added:
        return None
    _log.debug("added content: null to %d chat message(s)", added, extra={"event": "message_content"})
    return json.dumps(body).encode("utf-8")


class AddMissingContent:
    """ASGI middleware: rewrite the chat request body with :func:`normalize`."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope.get("type") != "http" or scope.get("path") != _PATH:
            await self.app(scope, receive, send)
            return
        chunks: list[bytes] = []
        while True:
            message = await receive()
            if message["type"] != "http.request":
                break
            chunks.append(message.get("body", b""))
            if not message.get("more_body", False):
                break
        raw = b"".join(chunks)
        fixed = normalize(raw)
        if fixed is not None:
            raw = fixed
            scope = dict(scope, headers=[(k, v) for k, v in scope.get("headers", [])
                                         if k.lower() != b"content-length"]
                         + [(b"content-length", str(len(raw)).encode())])
        sent = False

        async def replay() -> dict:
            nonlocal sent
            if sent:
                return {"type": "http.disconnect"}
            sent = True
            return {"type": "http.request", "body": raw, "more_body": False}

        await self.app(scope, replay, send)


def install(api_module: Any = None) -> bool:
    """Add the middleware to NeMo's server app once. False if NeMo is not importable."""
    if api_module is None:
        try:
            import nemoguardrails.server.api as api_module
        except Exception:
            _log.exception("message content patch skipped; NeMo server is not importable")
            return False
    if getattr(api_module, _PATCHED, False):
        return True
    app = getattr(api_module, "app", None)
    if app is None or not hasattr(app, "add_middleware"):
        return False
    app.add_middleware(AddMissingContent)
    setattr(api_module, _PATCHED, True)
    _log.info("NeMo message content patch applied", extra={"event": "message_content"})
    return True
