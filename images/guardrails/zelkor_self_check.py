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


def _record_span(side: str, attrs: Dict[str, Any]) -> None:
    """One span per check, so a trace shows the mode, the verdict and whether it was enforced."""
    from opentelemetry import trace

    with trace.get_tracer("zelkor-guardrails").start_as_current_span(f"guardrail self_check {side}", attributes=attrs):
        pass


def _tag(side: str, result: Dict[str, Any], latency_ms: float) -> None:
    fields = {"side": side, "mode": result["mode"], "verdict": result["verdict"] or "none",
              "status": result["status"], "enforced": result["enforced"],
              "on_unavailable": result["on_unavailable"], "latency_ms": latency_ms}
    attrs = {f"zelkor.guardrail.{k}": v for k, v in fields.items()}
    # Langfuse lists observation metadata; other OTLP backends show the zelkor.* attributes.
    attrs.update({f"langfuse.observation.metadata.guardrail_{k}": v for k, v in fields.items()})
    try:
        _record_span(side, attrs)
    except Exception:  # noqa: BLE001 - tracing never changes a verdict
        logger.debug("guardrail span not recorded", exc_info=True)


async def check(
    side: str,
    mode: str,
    timeout_ms: int,
    text: Optional[str],
    run_task: Callable[[], Awaitable[Tuple[Any, str]]],
    on_unavailable: str = "allow",
) -> Dict[str, Any]:
    """Run one self-check. ``on_unavailable=block`` refuses in block mode when the check gave no
    verdict (timeout, error, unparseable); it never applies to log mode."""
    result: Dict[str, Any] = {"blocked": False, "verdict": "", "status": "skipped", "mode": mode,
                              "enforced": False, "on_unavailable": on_unavailable}
    if not (text or "").strip():
        return result
    started = time.monotonic()
    answer: Optional[str] = None
    try:
        _, answer = await asyncio.wait_for(run_task(), timeout=timeout_ms / 1000.0)
    except asyncio.TimeoutError:
        result["status"] = "timeout"
    except Exception as exc:  # noqa: BLE001 - a failed check is a missing verdict, not a crash
        result["status"] = "error"
        result["exc_type"] = type(exc).__name__
    elapsed = time.monotonic() - started
    if result["status"] == "skipped":
        block = parse_verdict(answer)
        if block is None:
            result["status"] = "unparseable"
        else:
            result.update(status="ok", verdict="block" if block else "allow")
    if result["status"] == "ok":
        result["enforced"] = result["verdict"] == "block" and mode == "block"
        logger.info("guardrail_verdict", extra={
            "event": "guardrail_verdict", "kind": f"self_check:{mode}", "phase": side,
            "status": result["verdict"], "elapsed_s": round(elapsed, 3)})
    else:
        result["enforced"] = mode == "block" and on_unavailable == "block"
        event = "guardrail_unparseable" if result["status"] == "unparseable" else "guardrail_unavailable"
        logger.warning(event, extra={
            "event": event, "kind": f"self_check:{mode}", "phase": side, "status": result["status"],
            "exc_type": result.pop("exc_type", ""), "elapsed_s": round(elapsed, 3)})
    result.pop("exc_type", None)
    result["blocked"] = result["enforced"]
    _tag(side, result, round(elapsed * 1000, 1))
    return result
