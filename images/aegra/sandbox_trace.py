"""Stamp sandbox execution metadata on the current OTEL tool span."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("zelkor-aegra")


def _coerce_execution(value: Any) -> Optional[Dict[str, Any]]:
    if isinstance(value, dict):
        if value.get("execution"):
            nested = value.get("execution")
            return nested if isinstance(nested, dict) else None
        if value.get("outcome"):
            return value
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
