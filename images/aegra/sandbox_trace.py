"""Stamp sandbox execution metadata on the current OTEL tool span."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("zelkor-aegra")


def _block_text(block: Any) -> Optional[str]:
    """Text of one MCP content block (dict or TextContent-like object)."""
    if isinstance(block, dict):
        text = block.get("text") if block.get("type", "text") == "text" else None
    else:
        text = getattr(block, "text", None) if getattr(block, "type", "text") == "text" else None
    return text if isinstance(text, str) else None


def _coerce_execution(value: Any) -> Optional[Dict[str, Any]]:
    # LangChain MCP adapters deliver tool output as a list of content blocks
    # ([{type: "text", text: "<json>"}]) or a dict carrying that list as "content".
    if isinstance(value, (list, tuple)):
        for block in value:
            text = _block_text(block)
            execution = _coerce_execution(text) if text is not None else None
            if execution:
                return execution
        return None
    if isinstance(value, dict):
        if value.get("execution"):
            nested = value.get("execution")
            return nested if isinstance(nested, dict) else None
        if value.get("outcome"):
            return value
        content = value.get("content")
        if isinstance(content, (list, tuple)):
            return _coerce_execution(content)
    if isinstance(value, str):
        try:
            import json

            parsed = json.loads(value)
            return _coerce_execution(parsed)
        except Exception:
            return None
    return None


def stamp_sandbox_execution_span(result: Any) -> None:
    execution = _coerce_execution(result)
    if not execution:
        return
    try:
        from opentelemetry import trace
    except ImportError:
        return

    span = trace.get_current_span()
    if span is None or not span.is_recording():
        return

    outcome = str(execution.get("outcome") or "")
    violation = str(execution.get("violation") or "")
    code_sha = str(execution.get("code_sha") or "")

    if outcome:
        span.set_attribute("sandbox.outcome", outcome)
        span.set_attribute("langfuse.observation.metadata.sandbox.outcome", outcome)
    if violation and violation != "none":
        span.set_attribute("sandbox.violation", violation)
        span.set_attribute("langfuse.observation.metadata.sandbox.violation", violation)
    if code_sha:
        span.set_attribute("sandbox.code_sha", code_sha)
        span.set_attribute("langfuse.observation.metadata.code_sha", code_sha)

    errno_val = execution.get("errno")
    if errno_val is not None:
        span.set_attribute("sandbox.errno", int(errno_val))
    exc_type = execution.get("exc_type")
    if exc_type:
        span.set_attribute("sandbox.exc_type", str(exc_type))
