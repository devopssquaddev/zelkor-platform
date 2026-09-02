"""Route NeMo OTLP export by agent Langfuse public key (baggage / header).

Keeps graph+NeMo in one project when agents use extraProjects keys.
Stamps langfuse.trace.name / session / user on every NeMo span.
Drops parentless httpx CLIENT http send/receive (untitled one-span traces).
"""
from __future__ import annotations

import json
import logging
import os
from base64 import b64encode
from collections import defaultdict
from typing import Any, Dict, List, Sequence

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
    """True for parentless httpx CLIENT http send/receive (Langfuse one-span junk)."""
    name = str(getattr(span, "name", "") or "").lower()
    if "http send" not in name and "http receive" not in name:
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


def stamp_identity(span: Any, values: Dict[str, str]) -> None:
    for key, attr in IDENTITY_ATTRS:
        value = values.get(key)
        if not value:
            continue
        span.set_attribute(attr, value)
        if attr == "langfuse.user.id":
            span.set_attribute("user.id", value)
        if attr == "langfuse.session.id":
            span.set_attribute("session.id", value)


def install() -> None:
    if getattr(install, "_done", False):
        return
    install._done = True  # type: ignore[attr-defined]

    extra = parse_extra_otlp(os.getenv("LANGFUSE_EXTRA_OTLP", ""))
    default_pk = os.getenv("LANGFUSE_PUBLIC_KEY", "").strip()

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

    orig_export = OTLPSpanExporter.export

    def _kept(spans):  # type: ignore[no-untyped-def]
        return [span for span in spans if not is_orphan_http_client(span)]

    def _export(self, spans):  # type: ignore[no-untyped-def]
        spans = _kept(spans)
        if not spans:
            return SpanExportResult.SUCCESS
        if getattr(self, "_zelkor_route_leaf", False) or not extra:
            return orig_export(self, spans)
        buckets: Dict[str, List] = defaultdict(list)
        for span in spans:
            buckets[pk_from_span(span, default_pk)].append(span)
        result = SpanExportResult.SUCCESS
        for pk, group in buckets.items():
            if pk in extra:
                result = _leaf(pk, extra[pk]).export(group)
            else:
                result = orig_export(self, group)
        return result

    OTLPSpanExporter.export = _export  # type: ignore[method-assign]

    class _IdentityProcessor(SpanProcessor):
        def on_start(self, span, parent_context=None):  # type: ignore[no-untyped-def]
            values: Dict[str, str] = {}
            for key, _attr in IDENTITY_ATTRS:
                value = baggage.get_baggage(key, parent_context) if parent_context else None
                if not value:
                    value = baggage.get_baggage(key)
                if value:
                    values[key] = str(value)
            stamp_identity(span, values)

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

        FastAPI.__init__ = _fastapi_init  # type: ignore[method-assign]
    except Exception:
        _log.exception("NeMo Langfuse identity middleware failed")

    _log.info(
        "NeMo OTEL identity + orphan CLIENT drop enabled (extra keys=%s)",
        len(extra),
    )
