"""One run = one waterfall for runtimes we do not control (CE-14), in Langfuse or any OTLP backend.

The sidecar opens the run root span (named ``graph_id``) and records every LLM and MCP
hop it proxies as a child. Runtime-internal spans join only via the ``traceparent`` the
sidecar injects. Export: bundled Langfuse (OTLP HTTP, Basic pk:sk, ingestion v4) or a plain
OTLP endpoint; without OTEL deps or a target, tracing is a no-op.

Spans carry the standard set only (span name, ``user.id``, ``session.id``, ``gen_ai.*``,
``error.type``, status). Langfuse keys kept on purpose: ``langfuse.observation.type`` (Langfuse
has no standard source for TOOL / GENERATION) and ``langfuse.observation.metadata.*`` (CE-12
evaluators filter on it). Langfuse identity for NeMo travels as baggage, not span attributes.
"""
from __future__ import annotations

import base64
import json
import logging
import os
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional

logger = logging.getLogger("zelkor-sidecar")

# Standard identity on every span (ctx field -> attribute).
SPAN_IDENTITY = (("tenant_id", "user.id"), ("thread_id", "session.id"))


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
        """Span attributes: user.id / session.id (Langfuse v4 and OTLP backends read them per span)."""
        return {key: str(getattr(ctx, attr)) for attr, key in SPAN_IDENTITY if getattr(ctx, attr, "")}

    def _baggage(self, ctx: Any) -> Dict[str, str]:
        """Baggage for downstream hops: the standard identity, plus the trace name and Langfuse
        project key NeMo stamps in Langfuse mode (baggage, never attributes on our spans)."""
        out = self._identity(ctx)
        if getattr(ctx, "graph_id", ""):
            out["langfuse.trace.name"] = str(ctx.graph_id)
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
        # Langfuse trace metadata falls back to the root observation's metadata.
        span.set_attribute("langfuse.observation.metadata.tenant_id", ctx.tenant_id)
        span.set_attribute("langfuse.observation.metadata.runtime", getattr(ctx, "runtime", ""))
        if input_text:
            span.set_attribute("gen_ai.prompt", json.dumps(input_text))
        return span

    def end_root(self, span: Any, ctx: Any, *, output_text: str = "", error: str = "") -> None:
        if not span.is_recording():
            span.end()
            return
        from opentelemetry.trace import Status, StatusCode

        span.set_attribute("langfuse.observation.metadata.tool_names", json.dumps(list(ctx.tool_names)))
        if output_text:
            span.set_attribute("gen_ai.completion", json.dumps(output_text))
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
        """traceparent + baggage so NeMo joins the same trace; x-zelkor-langfuse-pk routes its export."""
        headers: Dict[str, str] = {}
        target = span if span is not None and span.is_recording() else ctx.root_span
        if self._tracer and target is not None and target.is_recording():
            from opentelemetry import baggage, trace
            from opentelemetry.propagate import inject

            carrier: Dict[str, str] = {}
            otel_ctx = trace.set_span_in_context(target)
            for key, value in self._baggage(ctx).items():
                otel_ctx = baggage.set_baggage(key, value, context=otel_ctx)
            inject(carrier, context=otel_ctx)
            headers.update(carrier)
        elif ctx.traceparent:
            headers["traceparent"] = ctx.traceparent
        if self.public_key:
            headers["x-zelkor-langfuse-pk"] = self.public_key
        return headers
