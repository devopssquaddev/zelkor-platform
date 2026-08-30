"""Normalize NeMo / intercept chat.completions bodies for langchain-openai 1.x.

NeMo Guardrails' OpenAI-compatible server may return `choices: null` plus a
`messages` array. langchain-openai 1.6+ raises TypeError on null choices.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

logger = logging.getLogger("zelkor-openai-compat")


def normalize_chat_completion(data: Any) -> Any:
    if not isinstance(data, dict):
        return data
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        return data
    messages = data.get("messages") or []
    assistant = None
    if isinstance(messages, list):
        for item in reversed(messages):
            if isinstance(item, dict) and item.get("role") == "assistant":
                assistant = item
                break
    if assistant is None:
        return data
    content = assistant.get("content") or assistant.get("refusal") or ""
    out = dict(data)
    out["choices"] = [
        {
            "index": 0,
            "message": {"role": "assistant", "content": content},
            "finish_reason": "stop",
        }
    ]
    return out


def _rewrite_bytes(raw: Optional[bytes]) -> Optional[bytes]:
    if not raw:
        return raw
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError, UnicodeDecodeError):
        return raw
    normalized = normalize_chat_completion(data)
    if normalized is data:
        return raw
    return json.dumps(normalized).encode("utf-8")


def patch_httpx() -> None:
    try:
        import httpx
    except ImportError:
        logger.info("openai_compat: httpx not installed")
        return

    orig_read = httpx.Response.read
    orig_aread = httpx.Response.aread
    orig_json = httpx.Response.json

    def read(self, *args, **kwargs):
        raw = orig_read(self, *args, **kwargs)
        rewritten = _rewrite_bytes(raw)
        if rewritten is not None and rewritten != raw:
            self._content = rewritten
            return rewritten
        return raw

    async def aread(self, *args, **kwargs):
        raw = await orig_aread(self, *args, **kwargs)
        rewritten = _rewrite_bytes(raw)
        if rewritten is not None and rewritten != raw:
            self._content = rewritten
            return rewritten
        return raw

    def json(self, **kwargs):
        data = orig_json(self, **kwargs)
        return normalize_chat_completion(data)

    httpx.Response.read = read  # type: ignore[method-assign]
    httpx.Response.aread = aread  # type: ignore[method-assign]
    httpx.Response.json = json  # type: ignore[method-assign]
    logger.info("openai_compat: patched httpx.Response for NeMo chat completions")
