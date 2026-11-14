"""Route NeMo OTLP export by agent Langfuse public key (baggage / header), or plain OTLP.

Langfuse mode (ingest keys set): keeps graph+NeMo in one project when agents use extraProjects
keys and stamps langfuse.trace.name / session / user on every NeMo span. OTLP mode (no Langfuse
keys, e.g. profile=perimeter): exports kept spans to OTEL_EXPORTER_OTLP_ENDPOINT and stamps only
the standard user.id / session.id.
Drops untitled CLIENT ``POST`` / ``http send`` roots (empty Langfuse rows).
Nested hops under FastAPI ``POST /v1/chat/completions`` stay.
"""
from __future__ import annotations

import json
import logging
import os
from base64 import b64encode
from collections import defaultdict
from typing import Any, Dict, List, Sequence

from langfuse_keep import LangfuseKeep, has_agent_identity, is_http_client_hop, span_trace_id

_log = logging.getLogger("zelkor-nemo-otel")
ATTR = "zelkor.langfuse.pk"
BAGGAGE_KEY = "zelkor.langfuse.pk"
HEADER = "x-zelkor-langfuse-pk"

IDENTITY_HEADERS: Sequence[tuple[str, str]] = (
    (HEADER, BAGGAGE_KEY),
    ("x-zelkor-langfuse-trace-name", "langfuse.trace.name"),
    ("x-zelkor-langfuse-session-id", "langfuse.session.id"),
    ("x-zelkor-langfuse-user-id", "langfuse.user.id"),
)
IDENTITY_ATTRS: Sequence[tuple[str, str]] = (
    (BAGGAGE_KEY, ATTR),
    ("langfuse.trace.name", "langfuse.trace.name"),
    ("langfuse.session.id", "langfuse.session.id"),
    ("langfuse.user.id", "langfuse.user.id"),
)
# Standard identity baggage (the sidecar and Aegra send it with W3C trace context).
STANDARD_BAGGAGE: Sequence[str] = ("user.id", "session.id")


def parse_extra_otlp(raw: str) -> Dict[str, str]:
    try:
        data = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, list):
        return {}
    out: Dict[str, str] = {}
    for item in data:
        if not isinstance(item, dict):
            continue
        pk = str(item.get("publicKey") or item.get("public_key") or "").strip()
        sk = str(item.get("secretKey") or item.get("secret_key") or "").strip()
        if pk and sk:
            out[pk] = sk
    return out


def basic_auth_header(pk: str, sk: str) -> str:
    return "Basic " + b64encode(f"{pk}:{sk}".encode("utf-8")).decode("ascii")


def traces_endpoint(base: str) -> str:
    """OTLPSpanExporter(endpoint=) is the traces URL; env base needs /v1/traces."""
    ep = (base or "").rstrip("/")
    if not ep:
        return ""
    if ep.endswith("/v1/traces"):
        return ep
    return ep + "/v1/traces"


def pk_from_span(span: Any, default: str) -> str:
    attrs = getattr(span, "attributes", None) or {}
    value = attrs.get(ATTR)
    if value:
        return str(value)
    return default


def is_orphan_http_client(span: Any) -> bool:
    """True for parentless untitled CLIENT hops (``POST``, ``http send``)."""
    name = str(getattr(span, "name", "") or "").strip()
    lowered = name.lower()
    parts = name.split()
    is_hop = "http send" in lowered or "http receive" in lowered
    is_bare_method = (
        bool(parts)
        and parts[0].upper()
        in {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"}
        and len(parts) == 1
    )
    if not is_hop and not is_bare_method:
        return False
    kind = getattr(span, "kind", None)
    kind_name = str(getattr(kind, "name", None) or kind)
    if "SERVER" in kind_name:
        return False
    parent = getattr(span, "parent", None)
    if parent is None:
        return True
    is_valid = getattr(parent, "is_valid", None)
    if callable(is_valid):
        return not is_valid()
    return False


_langfuse_keep = LangfuseKeep()


def drop_probe_span(span: Any) -> bool:
    """True when the span must not go to Langfuse."""
    return not _langfuse_keep.should_export(span)


def identity_from_headers(headers: Any) -> Dict[str, str]:
    out: Dict[str, str] = {}
    getter = headers.get if hasattr(headers, "get") else None
    if getter is None:
        return out
    for header, key in IDENTITY_HEADERS:
        value = getter(header) or getter(header.title())
        if value:
            out[key] = str(value)
    return out


def stamp_identity(span: Any, values: Dict[str, str], *, langfuse: bool = True) -> None:
    """Standard user.id / session.id always (from standard baggage, else the Langfuse keys);
    the langfuse.* identity and project pk only in Langfuse mode."""
    user = values.get("user.id") or values.get("langfuse.user.id")
    session = values.get("session.id") or values.get("langfuse.session.id")
    if user:
        span.set_attribute("user.id", user)
    if session:
        span.set_attribute("session.id", session)
    if not langfuse:
        return
    for key, attr in IDENTITY_ATTRS:
        value = values.get(key)
        if value:
            span.set_attribute(attr, value)
    if user and not values.get("langfuse.user.id"):
        span.set_attribute("langfuse.user.id", user)
    if session and not values.get("langfuse.session.id"):
        span.set_attribute("langfuse.session.id", session)


def _client_hop_of_kept_trace(span: Any) -> bool:
    if "SERVER" in str(getattr(getattr(span, "kind", None), "name", "") or ""):
        return False
    if not is_http_client_hop(span) or is_orphan_http_client(span):
        return False
    tid = span_trace_id(span)
    if not tid:
        return False
    if has_agent_identity(span):  # stamped by _IdentityProcessor; may end before any kept span
        _langfuse_keep._kept.add(tid)
        return True
    return tid in _langfuse_keep._kept


def kept_spans(spans: Sequence[Any], *, langfuse: bool) -> List[Any]:
    """Spans to export. Langfuse mode drops untitled HTTP hops (empty rows). OTLP mode keeps the
    CLIENT hops of a kept trace: the gateway's span for NeMo's own model call is their child."""
    batch = list(spans)
    kept = {id(s) for s in _langfuse_keep.filter_batch(batch) if not is_orphan_http_client(s)}
    if not langfuse:
        kept |= {id(s) for s in batch if id(s) not in kept and _client_hop_of_kept_trace(s)}
    return [s for s in batch if id(s) in kept]


def langfuse_mode() -> bool:
    """True when any Langfuse ingest key is configured (else plain OTLP export)."""
    extra, pk, sk = _ingest_credentials()
    return bool(extra) or bool(pk and sk)


def _ingest_credentials() -> tuple[Dict[str, str], str, str]:
    extra = parse_extra_otlp(os.getenv("LANGFUSE_EXTRA_OTLP", ""))
    default_pk = os.getenv("LANGFUSE_PUBLIC_KEY", "").strip()
    default_sk = os.getenv("LANGFUSE_SECRET_KEY", "").strip()
    return extra, default_pk, default_sk


def install() -> None:
    if getattr(install, "_done", False):
        return
    install._done = True  # type: ignore[attr-defined]

    extra, default_pk, default_sk = _ingest_credentials()

    from opentelemetry import baggage, context, trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.trace import SpanProcessor
    from opentelemetry.sdk.trace.export import SpanExportResult

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").rstrip("/")
    leaves: Dict[str, OTLPSpanExporter] = {}

    def _leaf(pk: str, sk: str) -> OTLPSpanExporter:
        if pk not in leaves:
            traces = traces_endpoint(endpoint)
            exp = OTLPSpanExporter(
                endpoint=traces or None,
                headers={"Authorization": basic_auth_header(pk, sk)},
            )
            exp._zelkor_route_leaf = True  # type: ignore[attr-defined]
            leaves[pk] = exp
        return leaves[pk]

    for pk, sk in extra.items():
        _leaf(pk, sk)
    if default_pk and default_sk:
        _leaf(default_pk, default_sk)

    orig_export = OTLPSpanExporter.export

    def _resolve_sk(pk: str) -> tuple[str, str]:
        extra_live, default_pk_live, default_sk_live = _ingest_credentials()
        effective = (pk or default_pk_live).strip()
        if not effective:
            return "", ""
        if effective in extra_live:
            return effective, extra_live[effective]
        if default_pk_live and default_sk_live:
            if effective == default_pk_live:
                return effective, default_sk_live
            # Agent stamped another project's pk we do not have — still export to default project.
            return default_pk_live, default_sk_live
        return "", ""

    def _kept(spans):  # type: ignore[no-untyped-def]
        return kept_spans(spans, langfuse=langfuse_mode())

    def _export(self, spans):  # type: ignore[no-untyped-def]
        spans = _kept(spans)
        if not spans:
            return SpanExportResult.SUCCESS
        if getattr(self, "_zelkor_route_leaf", False):
            return orig_export(self, spans)
        extra_live, default_pk_live, default_sk_live = _ingest_credentials()
        if not extra_live and not (default_pk_live and default_sk_live):
            return orig_export(self, spans)  # OTLP mode: one sink, no per-project routing
        buckets: Dict[str, List] = defaultdict(list)
        for span in spans:
            buckets[pk_from_span(span, default_pk_live)].append(span)
        result = SpanExportResult.SUCCESS
        for pk, group in buckets.items():
            route_pk, sk = _resolve_sk(pk)
            if route_pk and sk:
                result = _leaf(route_pk, sk).export(group)
            elif default_pk_live and default_sk_live:
                result = _leaf(default_pk_live, default_sk_live).export(group)
            else:
                _log.warning(
                    "NeMo OTLP export without Langfuse credentials (batch=%d spans)",
                    len(group),
                )
                result = orig_export(self, group)
        return result

    OTLPSpanExporter.export = _export  # type: ignore[method-assign]

    class _IdentityProcessor(SpanProcessor):
        def on_start(self, span, parent_context=None):  # type: ignore[no-untyped-def]
            values: Dict[str, str] = {}
            for key in [k for k, _attr in IDENTITY_ATTRS] + list(STANDARD_BAGGAGE):
                value = baggage.get_baggage(key, parent_context) if parent_context else None
                if not value:
                    value = baggage.get_baggage(key)
                if value:
                    values[key] = str(value)
            stamp_identity(span, values, langfuse=langfuse_mode())

        def on_end(self, span):  # type: ignore[no-untyped-def]
            return

        def shutdown(self):  # type: ignore[no-untyped-def]
            return

        def force_flush(self, timeout_millis=30000):  # type: ignore[no-untyped-def]
            return True

    def _add_processor(provider) -> None:
        if provider is None or not hasattr(provider, "add_span_processor"):
            return
        if getattr(provider, "_zelkor_pk_processor", False):
            return
        provider.add_span_processor(_IdentityProcessor())
        provider._zelkor_pk_processor = True  # type: ignore[attr-defined]

    orig_set = trace.set_tracer_provider

    def _set(provider):  # type: ignore[no-untyped-def]
        orig_set(provider)
        _add_processor(provider)

    trace.set_tracer_provider = _set  # type: ignore[method-assign]
    _add_processor(trace.get_tracer_provider())

    try:
        from fastapi import FastAPI

        orig_init = FastAPI.__init__

        def _fastapi_init(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            orig_init(self, *args, **kwargs)

            async def _identity_mw(request, call_next):  # type: ignore[no-untyped-def]
                values = identity_from_headers(request.headers)
                if not values:
                    return await call_next(request)
                ctx = context.get_current()
                for key, value in values.items():
                    ctx = baggage.set_baggage(key, value, context=ctx)
                token = context.attach(ctx)
                try:
                    return await call_next(request)
                finally:
                    context.detach(token)

            self.middleware("http")(_identity_mw)

            if os.getenv("ENABLE_PROMETHEUS_METRICS", "").lower() in ("1", "true", "yes"):
                try:
                    from prometheus_fastapi_instrumentator import Instrumentator

                    Instrumentator(
                        should_group_status_codes=False,
                        should_ignore_untemplated=True,
                        excluded_handlers=[
                            "/health",
                            "/v1/health",
                            "/metrics",
                            "/docs",
                            "/redoc",
                            "/openapi.json",
                        ],
                    ).instrument(self).expose(self, endpoint="/metrics", include_in_schema=False)
                except Exception:
                    _log.exception("NeMo Prometheus metrics failed")

        FastAPI.__init__ = _fastapi_init  # type: ignore[method-assign]
    except Exception:
        _log.exception("NeMo Langfuse identity middleware failed")

    _log.info(
        "NeMo OTEL identity + orphan CLIENT drop enabled (sink=%s, extra keys=%s)",
        "langfuse" if langfuse_mode() else "otlp",
        len(extra),
    )
