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
        if not (pk and sk and base and "LANGFUSE" in targets):
            logger.info("tracing disabled (no Langfuse target)", extra={"event": "startup"})
            return cls(tracer=None, public_key=pk)
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
        except ImportError:
            logger.warning("tracing disabled: opentelemetry not installed")
            return cls(tracer=None, public_key=pk)
        auth = base64.b64encode(f"{pk}:{sk}".encode()).decode()
        provider = TracerProvider(resource=Resource.create({"service.name": "zelkor-sidecar"}))
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(
            endpoint=f"{base}/api/public/otel/v1/traces",
            headers={"Authorization": f"Basic {auth}", "x-langfuse-ingestion-version": "4"},
        )))
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
            if key.startswith("langfuse."):
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
