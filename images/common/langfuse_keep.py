"""Langfuse OTEL export allowlist: agent identity or /v1/chat/completions.

Probes and Aegra inbound HTTP SERVER spans never export. Untitled NeMo
CLIENT hops (bare ``POST``, ``http send``) never independently keep a
trace. Other untitled HTTP is dropped unless the span already belongs
to a kept trace.
"""
from __future__ import annotations

import os
from collections import OrderedDict
from typing import Any, Iterable
from urllib.parse import urlparse

_DEFAULT_PROBE_PATHS = ("/health", "/live", "/ready", "/v1/health")
_PATH_ATTR_KEYS = ("http.route", "http.target", "url.path", "http.path", "http.url")
_IDENTITY_ATTRS = ("langfuse.trace.name", "langfuse.session.id", "run_id")
_HTTP_METHODS = frozenset(
    {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"}
)
_CHAT_PATH = "/v1/chat/completions"
_TRACE_CAP = 4096


def excluded_probe_paths() -> tuple[str, ...]:
    """Comma-separated paths from Helm OTEL exclude env."""
    for key in (
        "OTEL_PYTHON_FASTAPI_EXCLUDED_URLS",
        "OTEL_PYTHON_ASGI_EXCLUDED_URLS",
        "OTEL_PYTHON_EXCLUDED_URLS",
    ):
        raw = os.getenv(key, "").strip()
        if raw:
            return tuple(p.strip() for p in raw.split(",") if p.strip())
    return _DEFAULT_PROBE_PATHS


def normalize_http_path(value: str) -> str:
    text = value.strip()
    if "://" in text:
        text = urlparse(text).path
    path = text.split("?", 1)[0].rstrip("/")
    return path or "/"


def span_trace_id(span: Any) -> int | None:
    ctx = getattr(span, "context", None)
    if ctx is None:
        getter = getattr(span, "get_span_context", None)
        ctx = getter() if callable(getter) else None
    tid = getattr(ctx, "trace_id", None)
    return int(tid) if tid else None


def span_http_path(span: Any) -> str | None:
    name = str(getattr(span, "name", "") or "")
    parts = name.split(None, 1)
    if len(parts) == 2 and parts[0].upper() in _HTTP_METHODS:
        return normalize_http_path(parts[1])
    attrs = getattr(span, "attributes", None) or {}
    for key in _PATH_ATTR_KEYS:
        raw = attrs.get(key)
        if raw is None:
            continue
        return normalize_http_path(str(raw))
    return None


def is_probe_span(span: Any) -> bool:
    probes = {normalize_http_path(p) for p in excluded_probe_paths()}
    path = span_http_path(span)
    return path in probes if path else False


def has_agent_identity(span: Any) -> bool:
    attrs = getattr(span, "attributes", None) or {}
    for key in _IDENTITY_ATTRS:
        value = attrs.get(key)
        if value is not None and str(value).strip():
            return True
    return False


def is_http_client_hop(span: Any) -> bool:
    """httpx CLIENT send/receive or a bare METHOD name (``POST``).

    These never independently keep a trace. Nested hops under a kept
    ``POST /v1/chat/completions`` SERVER still export when the tid is kept.
    """
    name = str(getattr(span, "name", "") or "").strip()
    lowered = name.lower()
    if "http send" in lowered or "http receive" in lowered:
        return True
    parts = name.split()
    if parts and parts[0].upper() in _HTTP_METHODS and len(parts) == 1:
        return "SERVER" not in _span_kind_name(span)
    return False


def is_chat_completions_span(span: Any) -> bool:
    """True for the NeMo FastAPI SERVER hop, not a bare CLIENT ``POST``."""
    name = str(getattr(span, "name", "") or "").strip()
    lowered = name.lower()
    if "http send" in lowered or "http receive" in lowered:
        return False
    parts = name.split()
    if parts and parts[0].upper() in _HTTP_METHODS and len(parts) == 1:
        return False
    return span_http_path(span) == _CHAT_PATH


def _span_kind_name(span: Any) -> str:
    kind = getattr(span, "kind", None)
    return str(getattr(kind, "name", None) or kind or "")


def is_inbound_http_server(span: Any) -> bool:
    """Aegra FastAPI/ASGI SERVER hits — never independently keepable.

    Bare ``METHOD`` / ``METHOD /path`` names are inbound. Extra tokens
    (``POST /v1/chat/completions http send``) are client hops, not this.
    ``/v1/chat/completions`` stays keepable for NeMo.
    """
    if is_chat_completions_span(span):
        return False
    name = str(getattr(span, "name", "") or "").strip()
    parts = name.split()
    if parts and parts[0].upper() in _HTTP_METHODS and len(parts) <= 2:
        return True
    if "SERVER" not in _span_kind_name(span):
        return False
    attrs = getattr(span, "attributes", None) or {}
    if attrs.get("http.method") or attrs.get("http.route") or attrs.get("http.target"):
        return True
    return span_http_path(span) is not None


class TraceIdLru:
    def __init__(self, cap: int = _TRACE_CAP) -> None:
        self._cap = cap
        self._ids: OrderedDict[int, None] = OrderedDict()

    def add(self, tid: int) -> None:
        if tid in self._ids:
            self._ids.move_to_end(tid)
            return
        self._ids[tid] = None
        while len(self._ids) > self._cap:
            self._ids.popitem(last=False)

    def __contains__(self, tid: object) -> bool:
        return tid in self._ids

    def __len__(self) -> int:
        return len(self._ids)


class LangfuseKeep:
    """Process-local keep set so FastAPI/rail children join a kept parent."""

    def __init__(self, cap: int = _TRACE_CAP) -> None:
        self._kept = TraceIdLru(cap)

    def note(self, span: Any) -> bool:
        """Mark the trace if this span is independently keepable. Return keep."""
        if is_probe_span(span) or is_inbound_http_server(span):
            return False
        if is_http_client_hop(span):
            tid = span_trace_id(span)
            return bool(tid and tid in self._kept)
        if has_agent_identity(span) or is_chat_completions_span(span):
            tid = span_trace_id(span)
            if tid:
                self._kept.add(tid)
            return True
        tid = span_trace_id(span)
        return bool(tid and tid in self._kept)

    def should_export(self, span: Any) -> bool:
        if is_probe_span(span) or is_inbound_http_server(span):
            return False
        return self.note(span)

    def prepare_batch(self, spans: Iterable[Any]) -> None:
        """Mark keep ids before filtering a batch (children may precede roots)."""
        for span in spans:
            if is_probe_span(span) or is_inbound_http_server(span):
                continue
            if is_http_client_hop(span):
                continue
            if has_agent_identity(span) or is_chat_completions_span(span):
                tid = span_trace_id(span)
                if tid:
                    self._kept.add(tid)

    def filter_batch(self, spans: Iterable[Any]) -> list[Any]:
        batch = list(spans)
        self.prepare_batch(batch)
        return [span for span in batch if self.should_export(span)]
