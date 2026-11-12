"""One run = one Langfuse waterfall for runtimes we do not control (CE-14).

The sidecar opens the run root span (named ``graph_id``) and records every LLM and MCP
hop it proxies as a child. Runtime-internal spans join only via the ``traceparent`` the
sidecar injects. Export mirrors Aegra's Langfuse target (OTLP HTTP, Basic pk:sk,
ingestion v4). Without OTEL deps or Langfuse keys, tracing is a no-op.
"""
from __future__ import annotations

import base64
import json
import logging
import os
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional

logger = logging.getLogger("zelkor-sidecar")

IDENTITY_HEADERS = (
    ("graph_id", "langfuse.trace.name", "x-zelkor-langfuse-trace-name"),
    ("thread_id", "langfuse.session.id", "x-zelkor-langfuse-session-id"),
    ("tenant_id", "langfuse.user.id", "x-zelkor-langfuse-user-id"),
)


def _parse_otlp_headers(raw: str) -> Dict[str, str]:
    """OTEL_EXPORTER_OTLP_HEADERS form: 'k1=v1,k2=v2'."""
    out: Dict[str, str] = {}
    for part in (raw or "").split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            if k.strip():
                out[k.strip()] = v.strip()
    return out


def set_span_error(span: Any, message: str = "") -> None:
    """Mark a span failed with standard OTel status (no-op when tracing is off)."""
    try:
        from opentelemetry.trace import Status, StatusCode

        span.set_status(Status(StatusCode.ERROR, (message or "")[:200]))
    except Exception:
        pass


class _NoSpan:
    def set_attribute(self, *_a, **_k) -> None:
        return None

    def set_status(self, *_a, **_k) -> None:
        return None

    def end(self) -> None:
        return None

    def is_recording(self) -> bool:
        return False


class Tracing:
    def __init__(self, *, tracer: Any = None, public_key: str = "") -> None:
        self._tracer = tracer
        self.public_key = public_key or os.getenv("LANGFUSE_PUBLIC_KEY", "").strip()

    @classmethod
    def from_env(cls) -> "Tracing":
        pk = os.getenv("LANGFUSE_PUBLIC_KEY", "").strip()
        sk = os.getenv("LANGFUSE_SECRET_KEY", "").strip()
        base = os.getenv("LANGFUSE_BASE_URL", "").strip().rstrip("/")
        targets = os.getenv("OTEL_TARGETS", "").upper()
        otlp = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip().rstrip("/")
        langfuse_on = bool(pk and sk and base and "LANGFUSE" in targets)
        # CE-15a-3: perimeter has Langfuse off; export the same waterfall to a BYO OTLP
        # collector when OTEL_EXPORTER_OTLP_ENDPOINT is set (single sink; CE gate in the chart).
        if not langfuse_on and not otlp:
            logger.info("tracing disabled (no Langfuse or OTLP target)", extra={"event": "startup"})
            return cls(tracer=None, public_key=pk)
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
        except ImportError:
            logger.warning("tracing disabled: opentelemetry not installed")
            return cls(tracer=None, public_key=pk)
        provider = TracerProvider(resource=Resource.create({"service.name": "zelkor-sidecar"}))
        if langfuse_on:
            auth = base64.b64encode(f"{pk}:{sk}".encode()).decode()
            exporter = OTLPSpanExporter(
                endpoint=f"{base}/api/public/otel/v1/traces",
                headers={"Authorization": f"Basic {auth}", "x-langfuse-ingestion-version": "4"},
            )
            logger.info("tracing on (langfuse)", extra={"event": "startup"})
        else:
            endpoint = otlp if otlp.endswith("/v1/traces") else f"{otlp}/v1/traces"
            headers = _parse_otlp_headers(os.getenv("OTEL_EXPORTER_OTLP_HEADERS", ""))
            exporter = OTLPSpanExporter(endpoint=endpoint, headers=headers or None)
            logger.info("tracing on (otlp)", extra={"event": "startup"})
        provider.add_span_processor(BatchSpanProcessor(exporter))
        return cls(tracer=provider.get_tracer("zelkor.sidecar"), public_key=pk)

    @property
    def enabled(self) -> bool:
        return self._tracer is not None

    def _identity(self, ctx: Any) -> Dict[str, str]:
        out = {}
        for attr, key, _h in IDENTITY_HEADERS:
            value = getattr(ctx, attr, "")
            if value:
                out[key] = str(value)
        # CE-15a-3: standard identity read by both Langfuse v4.76 and generic OTLP backends.
        # The root span name (graph_id) is the Langfuse trace name; user/session ride every span.
        if getattr(ctx, "tenant_id", ""):
            out["user.id"] = str(ctx.tenant_id)
        if getattr(ctx, "thread_id", ""):
            out["session.id"] = str(ctx.thread_id)
        if self.public_key:
            out["zelkor.langfuse.pk"] = self.public_key
        return out

    def start_root(self, ctx: Any, *, input_text: str = "") -> Any:
        if not self._tracer:
            return _NoSpan()
        from opentelemetry import trace
        from opentelemetry.propagate import extract

        parent = extract({"traceparent": ctx.traceparent}) if ctx.traceparent else None
        span = self._tracer.start_span(ctx.graph_id, context=parent, kind=trace.SpanKind.INTERNAL)
        for key, value in self._identity(ctx).items():
            span.set_attribute(key, value)
        span.set_attribute("langfuse.trace.metadata.tenant_id", ctx.tenant_id)
        span.set_attribute("langfuse.trace.metadata.runtime", getattr(ctx, "runtime", ""))
        if input_text:
            span.set_attribute("langfuse.observation.input", json.dumps(input_text))
            span.set_attribute("langfuse.trace.input", json.dumps(input_text))
        return span

    def end_root(self, span: Any, ctx: Any, *, output_text: str = "", error: str = "") -> None:
        if not span.is_recording():
            span.end()
            return
        from opentelemetry.trace import Status, StatusCode

        span.set_attribute("langfuse.trace.metadata.tool_names", json.dumps(list(ctx.tool_names)))
        if output_text:
            span.set_attribute("langfuse.observation.output", json.dumps(output_text))
            span.set_attribute("langfuse.trace.output", json.dumps(output_text))
        if error:
            span.set_status(Status(StatusCode.ERROR, error[:200]))
        span.end()

    @contextmanager
    def child(self, ctx: Any, name: str, *, observation_type: str, kind: str = "CLIENT",
              attrs: Optional[Dict[str, Any]] = None) -> Iterator[Any]:
        if not self._tracer or ctx.root_span is None or not ctx.root_span.is_recording():
            yield _NoSpan()
            return
        from opentelemetry import trace

        parent = trace.set_span_in_context(ctx.root_span)
        span = self._tracer.start_span(name, context=parent, kind=getattr(trace.SpanKind, kind))
        # Langfuse v4 (events) and OTLP backends read identity per span, not only from the root.
        for key, value in self._identity(ctx).items():
            span.set_attribute(key, value)
        span.set_attribute("langfuse.observation.type", observation_type)
        for key, value in (attrs or {}).items():
            span.set_attribute(key, value)
        try:
            yield span
        finally:
            span.end()

    def propagation_headers(self, ctx: Any, span: Any = None) -> Dict[str, str]:
        """traceparent + baggage + x-zelkor-langfuse-* so NeMo joins the same trace."""
        headers: Dict[str, str] = {}
        target = span if span is not None and span.is_recording() else ctx.root_span
        if self._tracer and target is not None and target.is_recording():
            from opentelemetry import baggage, trace
            from opentelemetry.propagate import inject

            carrier: Dict[str, str] = {}
            otel_ctx = trace.set_span_in_context(target)
            for key, value in self._identity(ctx).items():
                otel_ctx = baggage.set_baggage(key, value, context=otel_ctx)
            inject(carrier, context=otel_ctx)
            headers.update(carrier)
        elif ctx.traceparent:
            headers["traceparent"] = ctx.traceparent
        identity = self._identity(ctx)
        if identity.get("zelkor.langfuse.pk"):
            headers["x-zelkor-langfuse-pk"] = identity["zelkor.langfuse.pk"]
        for _attr, key, header in IDENTITY_HEADERS:
            if identity.get(key):
                headers[header] = identity[key]
        return headers
