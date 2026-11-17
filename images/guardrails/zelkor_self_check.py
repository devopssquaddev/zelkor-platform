"""Self-check rails with a JSON verdict that never blocks by accident.

NeMo's own self-check parses a free-text Yes/No and treats an unclear answer as a block, so
instruction-following models refused ordinary requests. Here the model answers
``{"block": true|false}``; an unclear, slow or failed answer lets the request through and logs.
``mode=log`` records the verdict and never refuses; ``mode=block`` refuses on a block verdict.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple

from structured_output import json_object_payload

logger = logging.getLogger("zelkor-nemo")


def parse_verdict(raw: Optional[str]) -> Optional[bool]:
    """True = block, False = allow, None = no usable verdict."""
    payload = json_object_payload(raw or "")
    if payload is None:
        return None
    value = json.loads(payload).get("block")
    return value if isinstance(value, bool) else None


async def check(
    side: str,
    mode: str,
    timeout_ms: int,
    text: Optional[str],
    run_task: Callable[[], Awaitable[Tuple[Any, str]]],
) -> Dict[str, Any]:
    if not (text or "").strip():
        return {"blocked": False, "verdict": "", "status": "skipped"}
    started = time.monotonic()
    try:
        _, answer = await asyncio.wait_for(run_task(), timeout=timeout_ms / 1000.0)
    except Exception as exc:  # noqa: BLE001 - a failed check never blocks
        logger.warning("guardrail_unavailable", extra={
            "event": "guardrail_unavailable", "kind": "self_check", "phase": side,
            "exc_type": type(exc).__name__, "elapsed_s": round(time.monotonic() - started, 3)})
        return {"blocked": False, "verdict": "", "status": "unavailable"}
    block = parse_verdict(answer)
    if block is None:
        logger.warning("guardrail_unparseable", extra={
            "event": "guardrail_unparseable", "kind": "self_check", "phase": side})
        return {"blocked": False, "verdict": "", "status": "unparseable"}
    verdict = "block" if block else "allow"
    logger.info("guardrail_verdict", extra={
        "event": "guardrail_verdict", "kind": f"self_check:{mode}", "phase": side, "status": verdict,
        "elapsed_s": round(time.monotonic() - started, 3)})
    return {"blocked": block and mode == "block", "verdict": verdict, "status": "ok"}
