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


def bound_contextvars() -> dict[str, Any]:
    try:
        import structlog.contextvars as cv

        return dict(cv.get_contextvars() or {})
    except Exception:
        return {}


def bound_graph_id() -> str | None:
    gid = bound_contextvars().get("graph_id")
    if gid:
        return str(gid)
    return None


IDENTITY_KEYS = (
    ("graph_id", "langfuse.trace.name", "x-zelkor-langfuse-trace-name"),
    ("thread_id", "langfuse.session.id", "x-zelkor-langfuse-session-id"),
    ("user_id", "langfuse.user.id", "x-zelkor-langfuse-user-id"),
)


def run_identity(bindings: dict[str, Any] | None = None, *, public_key: str = "") -> dict[str, str]:
    """Langfuse identity for NeMo (baggage keys)."""
    src = bindings if bindings is not None else bound_contextvars()
    out: dict[str, str] = {}
    for src_key, baggage_key, _header in IDENTITY_KEYS:
        value = src.get(src_key)
        if value:
            out[baggage_key] = str(value)
    pk = (public_key or os.getenv("LANGFUSE_PUBLIC_KEY", "")).strip()
    if pk:
        out["zelkor.langfuse.pk"] = pk
    return out


def identity_headers(identity: dict[str, str]) -> dict[str, str]:
    headers = {}
    if identity.get("zelkor.langfuse.pk"):
        headers["x-zelkor-langfuse-pk"] = identity["zelkor.langfuse.pk"]
    for _src, baggage_key, header in IDENTITY_KEYS:
        value = identity.get(baggage_key)
        if value:
            headers[header] = value
    return headers


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


def _messages(value: Any, *, _depth: int = 0) -> list[Any]:
    if value is None or _depth > 8:
        return []
    if isinstance(value, dict):
        msgs = value.get("messages")
        if isinstance(msgs, list) and msgs:
            return msgs
        for key in (
            "payload",
            "checkpoint",
            "channel_values",
            "values",
            "data",
            "state",
            "update",
            "output",
        ):
            inner = value.get(key)
            if inner is not None and inner is not value:
                found = _messages(inner, _depth=_depth + 1)
                if found:
                    return found
        return []
    if isinstance(value, (list, tuple)) and value:
        if _role(value[0]):
            return list(value)
        return _messages(value[-1], _depth=_depth + 1)
    msgs = getattr(value, "messages", None)
    if isinstance(msgs, list) and msgs:
        return msgs
    return []


def user_prompt_text(value: Any) -> str:
    human = [stringify(m) for m in _messages(value) if _role(m) in ("human", "user")]
    human = [h for h in human if h]
    if human:
        return "\n".join(human)
    return stringify(value)


def assistant_output_text(value: Any) -> str:
    """Last assistant message. Empty for checkpoint metadata (do not stringify)."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)) and value and not _role(value[0] if value else None):
        for item in reversed(value):
            text = assistant_output_text(item)
            if text:
                return text
        return ""
    ai = [stringify(m) for m in _messages(value) if _role(m) in ("ai", "assistant")]
    ai = [a for a in ai if a]
    if ai:
        return ai[-1]
    return ""


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


def _run_manager_from(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
    rm = kwargs.get("run_manager")
    if rm is not None:
        return rm
    for item in args:
        if getattr(item, "run_id", None) is not None and (
            getattr(item, "handlers", None) is not None
            or getattr(item, "inheritable_handlers", None) is not None
        ):
            return item
    return None


def openinference_span_for_run(run_manager: Any) -> Any:
    """OpenInference starts spans without attach(); look them up by LangChain run_id."""
    run_id = getattr(run_manager, "run_id", None) if run_manager is not None else None
    if run_id is not None:
        handlers = list(getattr(run_manager, "handlers", None) or [])
        handlers.extend(getattr(run_manager, "inheritable_handlers", None) or [])
        for handler in handlers:
            getter = getattr(handler, "get_span", None)
            if callable(getter):
                span = getter(run_id)
                if span is not None:
                    return span
            spans = getattr(handler, "_spans_by_run", None)
            if isinstance(spans, dict) and run_id in spans:
                return spans[run_id]
        try:
            from openinference.instrumentation.langchain import LangChainInstrumentor

            span = LangChainInstrumentor().get_span(run_id)
            if span is not None:
                return span
        except Exception:
            pass
    return _recording_openinference_span("ChatOpenAI")


def _recording_openinference_span(name_substr: str) -> Any:
    try:
        from openinference.instrumentation.langchain import LangChainInstrumentor

        tracer = getattr(LangChainInstrumentor(), "_tracer", None)
        spans = getattr(tracer, "_spans_by_run", None) or {}
        for span in list(spans.values()):
            name = str(getattr(span, "name", "") or "")
            if name_substr.lower() in name.lower() and getattr(span, "is_recording", lambda: False)():
                return span
    except Exception:
        return None
    return None


def span_context(span: Any) -> Any:
    from opentelemetry import trace

    if span is None:
        return None
    return trace.set_span_in_context(span)


def attach_langfuse_project_baggage() -> None:
    """Stamp the worker's Langfuse public key so NeMo can export to the same project."""
    pk = os.getenv("LANGFUSE_PUBLIC_KEY", "").strip()
    if not pk:
        return
    from opentelemetry import baggage, context

    context.attach(baggage.set_baggage("zelkor.langfuse.pk", pk))


def inject_traceparent(headers: Any) -> None:
    """W3C inject + Langfuse identity. Must not require a recording current span."""
    from opentelemetry import baggage, context
    from opentelemetry.propagate import inject

    ctx = context.get_current()
    identity = run_identity()
    for key, value in identity.items():
        ctx = baggage.set_baggage(key, value, context=ctx)
    carrier: dict[str, str] = {}
    inject(carrier, context=ctx)
    tp = carrier.get("traceparent") or carrier.get("Traceparent")
    if not tp:
        return
    parts = tp.split("-")
    if len(parts) < 2 or set(parts[1]) <= {"0"}:
        return
    for key, value in carrier.items():
        headers[key] = value
    for key, value in identity_headers(identity).items():
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
            last_text = ""
            for item in orig_stream(self, *args, **kwargs):
                text = assistant_output_text(item)
                if text:
                    last_text = text
                yield item
            record_span_io(span, completion=last_text)

    async def astream(self, *args, **kwargs):
        payload = _call_input(args, kwargs)
        with tracer.start_as_current_span(run_span_name(self)) as span:
            record_span_io(span, prompt=user_prompt_text(payload))
            last_text = ""
            async for item in orig_astream(self, *args, **kwargs):
                text = assistant_output_text(item)
                if text:
                    last_text = text
                yield item
            record_span_io(span, completion=last_text)

    async def astream_events(self, *args, **kwargs):
        payload = _call_input(args, kwargs)
        with tracer.start_as_current_span(run_span_name(self)) as span:
            record_span_io(span, prompt=user_prompt_text(payload))
            last_text = ""
            async for item in orig_astream_events(self, *args, **kwargs):
                text = assistant_output_text(item)
                if text:
                    last_text = text
                yield item
            record_span_io(span, completion=last_text)

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

    def _request_span(args: tuple[Any, ...], kwargs: dict[str, Any]):
        return tracer.start_as_current_span(
            "ChatOpenAI.request",
            context=span_context(openinference_span_for_run(_run_manager_from(args, kwargs))),
            kind=trace.SpanKind.CLIENT,
        )

    def _generate(self, *args, **kwargs):
        with _request_span(args, kwargs):
            return orig_generate(self, *args, **kwargs)

    async def _agenerate(self, *args, **kwargs):
        with _request_span(args, kwargs):
            return await orig_agenerate(self, *args, **kwargs)

    BaseChatOpenAI._generate = _generate  # type: ignore[method-assign]
    BaseChatOpenAI._agenerate = _agenerate  # type: ignore[method-assign]
    if hasattr(BaseChatOpenAI, "_stream"):
        orig_stream = BaseChatOpenAI._stream

        def _stream(self, *args, **kwargs):
            with _request_span(args, kwargs):
                yield from orig_stream(self, *args, **kwargs)

        BaseChatOpenAI._stream = _stream  # type: ignore[method-assign]
    if hasattr(BaseChatOpenAI, "_astream"):
        orig_astream = BaseChatOpenAI._astream

        async def _astream(self, *args, **kwargs):
            with _request_span(args, kwargs):
                async for item in orig_astream(self, *args, **kwargs):
                    yield item

        BaseChatOpenAI._astream = _astream  # type: ignore[method-assign]
    BaseChatOpenAI._zelkor_current_span_wrapped = True  # type: ignore[attr-defined]


def wrap_tool_current_span(provider: Any) -> None:
    """Attach OpenInference tool span as current so MCP HTTP / children nest under it."""
    from opentelemetry import context as context_api
    from opentelemetry import trace

    try:
        from langchain_core.tools.base import BaseTool
    except ImportError:
        return
    if getattr(BaseTool, "_zelkor_tool_span_wrapped", False):
        return

    orig_run = getattr(BaseTool, "_run", None)
    orig_arun = getattr(BaseTool, "_arun", None)

    def _attach(run_manager: Any):
        span = openinference_span_for_run(run_manager)
        if span is None:
            return None
        return context_api.attach(trace.set_span_in_context(span))

    if callable(orig_run):

        def _run(self, *args, **kwargs):
            token = _attach(_run_manager_from(args, kwargs))
            try:
                return orig_run(self, *args, **kwargs)
            finally:
                if token is not None:
                    context_api.detach(token)

        BaseTool._run = _run  # type: ignore[method-assign]

    if callable(orig_arun):

        async def _arun(self, *args, **kwargs):
            token = _attach(_run_manager_from(args, kwargs))
            try:
                return await orig_arun(self, *args, **kwargs)
            finally:
                if token is not None:
                    context_api.detach(token)

        BaseTool._arun = _arun  # type: ignore[method-assign]

    BaseTool._zelkor_tool_span_wrapped = True  # type: ignore[attr-defined]


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
        try:
            wrap_tool_current_span(provider)
        except Exception:
            _log.exception("tool current-span wrap failed")

    _otel_setup._zelkor_httpx_patched = True  # type: ignore[attr-defined]
    OpenTelemetryProvider.setup = _otel_setup  # type: ignore[method-assign]
