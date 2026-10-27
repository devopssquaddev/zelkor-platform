"""CE-9 native MCP tool policy: name/prefix deny list and per-(tenant, tool) rate limit.

Helm renders ``workspace.tools.policy`` into per-backend env (bare tool names, no
``<backend>__`` prefix). Envoy enforces the same deny list first; this is defense in
depth for native backends. MCP ``readOnlyHint`` / ``destructiveHint`` are never read.
"""
from __future__ import annotations

import os
import threading
import time
from collections import OrderedDict
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple


class ToolPolicy:
    """Deny by exact name, ``prefix*``, or ``*`` (every tool on this backend)."""

    def __init__(self, patterns: Iterable[str]) -> None:
        self._exact: set[str] = set()
        self._prefixes: List[str] = []
        for raw in patterns:
            pattern = str(raw).strip()
            if not pattern:
                continue
            if pattern.endswith("*"):
                self._prefixes.append(pattern[:-1])
            else:
                self._exact.add(pattern)

    @classmethod
    def from_env(cls) -> "ToolPolicy":
        return cls(os.getenv("MCP_DENY_TOOLS", "").split(","))

    def deny_reason(self, name: str) -> Optional[str]:
        if name in self._exact or any(name.startswith(p) for p in self._prefixes):
            return "policy"
        return None

    def filter_tools(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [t for t in tools if self.deny_reason(str(t.get("name", ""))) is None]


class RateLimiter:
    """Token bucket per (tenant, tool): ``per_minute`` capacity, refilled continuously.

    In memory, per pod. ``per_minute <= 0`` disables the limit. The least recently
    used keys are dropped past ``max_keys`` so a tenant/tool spray cannot grow memory.
    """

    def __init__(
        self,
        per_minute: int,
        *,
        max_keys: int = 10000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.per_minute = int(per_minute)
        self._max_keys = max(1, int(max_keys))
        self._clock = clock
        self._buckets: "OrderedDict[Tuple[str, str], Tuple[float, float]]" = OrderedDict()
        self._lock = threading.Lock()

    @classmethod
    def from_env(cls) -> "RateLimiter":
        return cls(int(os.getenv("MCP_RATE_LIMIT_PER_MINUTE", "0") or 0))

    def __len__(self) -> int:
        return len(self._buckets)

    def allow(self, tenant_id: str, tool: str) -> bool:
        if self.per_minute <= 0:
            return True
        key = (tenant_id, tool)
        now = self._clock()
        with self._lock:
            tokens, last = self._buckets.pop(key, (float(self.per_minute), now))
            tokens = min(float(self.per_minute), tokens + (now - last) * self.per_minute / 60.0)
            allowed = tokens >= 1.0
            if allowed:
                tokens -= 1.0
            self._buckets[key] = (tokens, now)
            while len(self._buckets) > self._max_keys:
                self._buckets.popitem(last=False)
        return allowed
