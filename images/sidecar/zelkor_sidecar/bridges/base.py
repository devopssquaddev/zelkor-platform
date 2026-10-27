"""Runtime bridge interface: how the sidecar drives the runtime on 127.0.0.1:8080."""
from __future__ import annotations

from typing import Any, AsyncIterator, Dict, List

from ..events import RuntimeEvent


class Bridge:
    """One adapter per runtime protocol (generic A2A, OpenCode, ...).

    ``send_turn`` gets the stored thread history (already including this turn's new
    messages) and yields ``message`` / ``error`` events. Tool events come from the
    egress proxy, not from bridges. A bridge may reuse a runtime session id
    (``ctx.runtime_session_id``) and must rebuild context from ``history`` when that
    session is gone; it sets ``ctx.runtime_session_id`` to the id it used.
    """

    name = "base"

    async def ready(self) -> bool:
        return True

    async def send_turn(self, ctx: Any, *, history: List[Dict[str, Any]],
                        new_messages: List[Dict[str, Any]]) -> AsyncIterator[RuntimeEvent]:
        raise NotImplementedError
        yield  # pragma: no cover

    async def abort(self, ctx: Any) -> None:
        return None

    async def close(self) -> None:
        return None
