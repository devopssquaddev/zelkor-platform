"""Normalized runtime events: what every bridge yields and the sidecar persists/streams."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class RuntimeEvent:
    """kind: tool_start | tool_end | message | error.

    ``key`` is idempotent per run (a replayed runtime event with the same key is stored
    once). Bridges derive it from the runtime's own event id when it has one.
    """

    kind: str
    data: Dict[str, Any] = field(default_factory=dict)
    key: str = field(default_factory=lambda: uuid.uuid4().hex)


def ai_message(content: Any, msg_id: Optional[str] = None, **extra: Any) -> Dict[str, Any]:
    msg = {"type": "ai", "content": content, "id": msg_id or f"msg-{uuid.uuid4().hex}"}
    msg.update(extra)
    return msg


def normalize_input_messages(payload: Any) -> List[Dict[str, Any]]:
    """Agent Protocol run input -> stored LangChain-style message dicts (role/type, content, id)."""
    raw = []
    if isinstance(payload, dict):
        raw = payload.get("messages") or []
    out = []
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, str):
            item = {"role": "human", "content": item}
        if not isinstance(item, dict):
            continue
        role = str(item.get("type") or item.get("role") or "human").lower()
        role = {"user": "human", "assistant": "ai"}.get(role, role)
        out.append({"type": role, "content": item.get("content", ""),
                    "id": str(item.get("id") or f"msg-{uuid.uuid4().hex}")})
    return out


def text_of(message: Dict[str, Any]) -> str:
    """Plain text of a stored message (content may be a string or a list of blocks)."""
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type", "text") == "text":
                parts.append(str(block.get("text", "")))
        return "".join(parts)
    return "" if content is None else str(content)
