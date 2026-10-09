"""Surface the inner error when anyio wraps one failure in a TaskGroup."""

from __future__ import annotations

_TASKGROUP = "unhandled errors in a TaskGroup"


def root_cause(exc: BaseException) -> BaseException:
    """Walk a single-child ExceptionGroup down to the original error."""
    seen: set[int] = set()
    cur = exc
    while isinstance(cur, BaseExceptionGroup) and len(cur.exceptions) == 1:
        if id(cur) in seen:
            break
        seen.add(id(cur))
        cur = cur.exceptions[0]
    return cur


def public_message(exc: BaseException) -> str:
    inner = root_cause(exc)
    text = str(inner).strip()
    if text and _TASKGROUP not in text:
        return text
    if isinstance(inner, BaseExceptionGroup) and inner.exceptions:
        parts = [public_message(item) for item in inner.exceptions]
        joined = "; ".join(part for part in parts if part and _TASKGROUP not in part)
        if joined:
            return joined
    return text or type(inner).__name__


def install_stream_unwrap() -> None:
    """Re-raise the inner exception from graph streaming so /runs/wait is not a TaskGroup string."""
    import aegra_api.services.graph_streaming as graph_streaming

    current = graph_streaming.stream_graph_events
    if getattr(current, "_zelkor_unwrap", False):
        return
    orig = current

    async def stream_graph_events(*args, **kwargs):
        try:
            async for item in orig(*args, **kwargs):
                yield item
        except BaseException as exc:
            raise root_cause(exc) from None

    stream_graph_events._zelkor_unwrap = True  # type: ignore[attr-defined]
    graph_streaming.stream_graph_events = stream_graph_events
