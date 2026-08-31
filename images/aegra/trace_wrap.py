"""Aegra wrap: one Pregel run span as the OTEL root; ChatOpenAI HTTP is a child.

Graphs do not import Langfuse. Identity (user / session / graph / run_id) is
stamped by Aegra SpanEnrichmentProcessor from set_trace_context. This module
records observation I/O on the run root (Langfuse v4 maps gen_ai.content.*
and langfuse.observation.* onto observation input/output).
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

_log = logging.getLogger("zelkor-aegra-wrap")

IO_MAX = 8192


def bound_graph_id() -> str | None:
    try:
        import structlog.contextvars as cv

        gid = cv.get_contextvars().get("graph_id")
        if gid:
            return str(gid)
    except Exception:
        return None
    return None


def run_span_name(graph: Any) -> str:
    """Pregel root name is graph_id when Aegra bound it; else graph.name / env."""
    gid = bound_graph_id()
    if gid:
        return gid
    name = getattr(graph, "name", None)
    if isinstance(name, str) and name.strip() and name not in ("LangGraph",):
        return name
    env = os.getenv("ZELKOR_GRAPH_ID", "").strip()
    if env:
        return env
    if isinstance(name, str) and name.strip():
        return name
    return "LangGraph"


def clip_io(text: str, limit: int = IO_MAX) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "…"


def stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        content = value.get("content")
        if isinstance(content, str):
            return content
        if content is not None:
            return stringify(content)
    content = getattr(value, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and part.get("text"):
                parts.append(str(part["text"]))
        if parts:
            return "\n".join(parts)
    try:
        return json.dumps(value, default=str, ensure_ascii=False)
    except TypeError:
        return str(value)


def _role(msg: Any) -> str:
    if isinstance(msg, dict):
        return str(msg.get("role") or msg.get("type") or "").lower()
    return str(getattr(msg, "type", None) or getattr(msg, "role", None) or "").lower()


def _messages(value: Any) -> list[Any]:
    if isinstance(value, dict):
        msgs = value.get("messages")
        if isinstance(msgs, list):
            return msgs
        data = value.get("data")
        if isinstance(data, dict):
            return _messages(data)
        output = value.get("output")
        if output is not None and output is not value:
            return _messages(output)
    if isinstance(value, list) and value and _role(value[0]):
        return value
    msgs = getattr(value, "messages", None)
    if isinstance(msgs, list):
        return msgs
    return []


def user_prompt_text(value: Any) -> str:
    human = [stringify(m) for m in _messages(value) if _role(m) in ("human", "user")]
    human = [h for h in human if h]
    if human:
        return "\n".join(human)
    return stringify(value)


def assistant_output_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)) and value and not _role(value[0] if value else None):
        return assistant_output_text(value[-1])
    ai = [stringify(m) for m in _messages(value) if _role(m) in ("ai", "assistant")]
    ai = [a for a in ai if a]
    if ai:
        return ai[-1]
    return stringify(value)


def record_span_io(span: Any, *, prompt: str | None = None, completion: str | None = None) -> None:
    """Langfuse v4 observation I/O: attributes + gen_ai.content.* events."""
    if prompt:
        text = clip_io(prompt)
        span.set_attribute("langfuse.observation.input", text)
        span.set_attribute("input.value", text)
        span.add_event("gen_ai.content.prompt", {"content": text})
    if completion:
        text = clip_io(completion)
        span.set_attribute("langfuse.observation.output", text)
        span.set_attribute("output.value", text)
        span.add_event("gen_ai.content.completion", {"content": text})


def _call_input(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
    if args:
        return args[0]
    return kwargs.get("input")


def inject_traceparent(headers: Any) -> None:
    """W3C inject. Must not require a recording current span (OpenInference HTTP)."""
    from opentelemetry.propagate import inject

    carrier: dict[str, str] = {}
    inject(carrier)
    tp = carrier.get("traceparent") or carrier.get("Traceparent")
    if not tp:
        return
    parts = tp.split("-")
    if len(parts) < 2 or set(parts[1]) <= {"0"}:
        return
    for key, value in carrier.items():
        headers[key] = value


def patch_http_clients() -> None:
    def _patch_client_send(mod: Any) -> None:
        if not getattr(mod.Client.send, "_zelkor_traceparent", False):
            orig_send = mod.Client.send

            def _send(self, request, *args, **kwargs):
                inject_traceparent(request.headers)
                return orig_send(self, request, *args, **kwargs)

            _send._zelkor_traceparent = True  # type: ignore[attr-defined]
            mod.Client.send = _send  # type: ignore[method-assign]
        if not getattr(mod.AsyncClient.send, "_zelkor_traceparent", False):
            orig_asend = mod.AsyncClient.send

            async def _asend(self, request, *args, **kwargs):
                inject_traceparent(request.headers)
                return await orig_asend(self, request, *args, **kwargs)

            _asend._zelkor_traceparent = True  # type: ignore[attr-defined]
            mod.AsyncClient.send = _asend  # type: ignore[method-assign]

    import httpx

    _patch_client_send(httpx)
    try:
        import httpx2

        _patch_client_send(httpx2)
    except ImportError:
        _log.info("httpx2 not installed; OpenAI 3.x LLM inject skipped")


def wrap_pregel_current_span(provider: Any) -> None:
    from langgraph.pregel import Pregel
    from opentelemetry import trace

    if getattr(Pregel, "_zelkor_run_span_wrapped", False):
        return
    tracer = trace.get_tracer("zelkor.aegra", tracer_provider=provider)

    orig_invoke = Pregel.invoke
    orig_ainvoke = Pregel.ainvoke
    orig_stream = Pregel.stream
    orig_astream = Pregel.astream
    orig_astream_events = Pregel.astream_events

    def invoke(self, *args, **kwargs):
        payload = _call_input(args, kwargs)
        with tracer.start_as_current_span(run_span_name(self)) as span:
            record_span_io(span, prompt=user_prompt_text(payload))
            result = orig_invoke(self, *args, **kwargs)
            record_span_io(span, completion=assistant_output_text(result))
            return result

    async def ainvoke(self, *args, **kwargs):
        payload = _call_input(args, kwargs)
        with tracer.start_as_current_span(run_span_name(self)) as span:
            record_span_io(span, prompt=user_prompt_text(payload))
            result = await orig_ainvoke(self, *args, **kwargs)
            record_span_io(span, completion=assistant_output_text(result))
            return result

    def stream(self, *args, **kwargs):
        payload = _call_input(args, kwargs)
        with tracer.start_as_current_span(run_span_name(self)) as span:
            record_span_io(span, prompt=user_prompt_text(payload))
            last = None
            for item in orig_stream(self, *args, **kwargs):
                last = item
                yield item
            record_span_io(span, completion=assistant_output_text(last))

    async def astream(self, *args, **kwargs):
        payload = _call_input(args, kwargs)
        with tracer.start_as_current_span(run_span_name(self)) as span:
            record_span_io(span, prompt=user_prompt_text(payload))
            last = None
            async for item in orig_astream(self, *args, **kwargs):
                last = item
                yield item
            record_span_io(span, completion=assistant_output_text(last))

    async def astream_events(self, *args, **kwargs):
        payload = _call_input(args, kwargs)
        with tracer.start_as_current_span(run_span_name(self)) as span:
            record_span_io(span, prompt=user_prompt_text(payload))
            last = None
            async for item in orig_astream_events(self, *args, **kwargs):
                last = item
                yield item
            record_span_io(span, completion=assistant_output_text(last))

    Pregel.invoke = invoke  # type: ignore[method-assign]
    Pregel.ainvoke = ainvoke  # type: ignore[method-assign]
    Pregel.stream = stream  # type: ignore[method-assign]
    Pregel.astream = astream  # type: ignore[method-assign]
    Pregel.astream_events = astream_events  # type: ignore[method-assign]
    Pregel._zelkor_run_span_wrapped = True  # type: ignore[attr-defined]


def wrap_chat_openai_current_span(provider: Any) -> None:
    from langchain_openai.chat_models.base import BaseChatOpenAI
    from opentelemetry import trace

    if getattr(BaseChatOpenAI, "_zelkor_current_span_wrapped", False):
        return
    tracer = trace.get_tracer("zelkor.aegra", tracer_provider=provider)
    orig_generate = BaseChatOpenAI._generate
    orig_agenerate = BaseChatOpenAI._agenerate

    def _generate(self, *args, **kwargs):
        with tracer.start_as_current_span("ChatOpenAI.request", kind=trace.SpanKind.CLIENT):
            return orig_generate(self, *args, **kwargs)

    async def _agenerate(self, *args, **kwargs):
        with tracer.start_as_current_span("ChatOpenAI.request", kind=trace.SpanKind.CLIENT):
            return await orig_agenerate(self, *args, **kwargs)

    BaseChatOpenAI._generate = _generate  # type: ignore[method-assign]
    BaseChatOpenAI._agenerate = _agenerate  # type: ignore[method-assign]
    BaseChatOpenAI._zelkor_current_span_wrapped = True  # type: ignore[attr-defined]


def patch_otel_setup() -> None:
    """After Aegra TracerProvider exists: Pregel root + ChatOpenAI.request child.

    Do not enable HTTPXClientInstrumentor — it opens sibling roots named as the
    graph (MCP POST / other httpx) instead of nesting under the run span.
    """
    from aegra_api.observability.otel import OpenTelemetryProvider

    if getattr(OpenTelemetryProvider.setup, "_zelkor_httpx_patched", False):
        return

    orig = OpenTelemetryProvider.setup

    def _otel_setup(self):
        orig(self)
        provider = getattr(self, "_tracer_provider", None)
        if provider is None:
            return
        try:
            wrap_pregel_current_span(provider)
        except Exception:
            _log.exception("Pregel current-span wrap failed")
        try:
            wrap_chat_openai_current_span(provider)
        except Exception:
            _log.exception("ChatOpenAI current-span wrap failed")

    _otel_setup._zelkor_httpx_patched = True  # type: ignore[attr-defined]
    OpenTelemetryProvider.setup = _otel_setup  # type: ignore[method-assign]
