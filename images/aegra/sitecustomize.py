"""Auto-loaded wrap: auth.path inject, Mode B MCP inject."""
import logging
import os
import sys

_log = logging.getLogger("zelkor-aegra-wrap")

# This file lives in site-packages. Wrap modules live in /app (WORKDIR).
if "/app" not in sys.path:
    sys.path.insert(0, "/app")

try:
    from auth_inject import ensure_auth_config

    ensure_auth_config()
except Exception:
    _log.exception("auth.path inject failed")

# NeMo /v1 rejects tools + stream even with passthrough. Graph SSE still works;
# only the LLM HTTP call is non-streaming.
try:
    from langchain_openai import ChatOpenAI

    if not getattr(ChatOpenAI, "_zelkor_nonstream_patched", False):
        _orig_chat_openai_init = ChatOpenAI.__init__

        def _chat_openai_init(self, *args, **kwargs):
            kwargs.setdefault("disable_streaming", True)
            return _orig_chat_openai_init(self, *args, **kwargs)

        ChatOpenAI.__init__ = _chat_openai_init  # type: ignore[method-assign]
        ChatOpenAI._zelkor_nonstream_patched = True  # type: ignore[attr-defined]
except Exception:
    _log.exception("ChatOpenAI non-stream patch failed")

# Inject W3C traceparent on httpx and OpenAI 3.x httpx2 (LLM uses httpx2, not httpx).
# OpenInference records LLM observations via callbacks; it does not attach an
# OTEL current span during the HTTP call, so inject must not require is_recording.
try:
    from opentelemetry.propagate import inject

    def _inject_traceparent(headers) -> None:
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

    def _patch_client_send(mod) -> None:
        if not getattr(mod.Client.send, "_zelkor_traceparent", False):
            orig_send = mod.Client.send

            def _send(self, request, *args, **kwargs):
                _inject_traceparent(request.headers)
                return orig_send(self, request, *args, **kwargs)

            _send._zelkor_traceparent = True  # type: ignore[attr-defined]
            mod.Client.send = _send  # type: ignore[method-assign]
        if not getattr(mod.AsyncClient.send, "_zelkor_traceparent", False):
            orig_asend = mod.AsyncClient.send

            async def _asend(self, request, *args, **kwargs):
                _inject_traceparent(request.headers)
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
except Exception:
    _log.exception("httpx/httpx2 traceparent inject failed")

# Client spans after Aegra's TracerProvider exists. Attach a current span around
# BaseChatOpenAI generate (LangChain 1.x implements _agenerate on the base class).
try:
    from aegra_api.observability.otel import OpenTelemetryProvider

    if not getattr(OpenTelemetryProvider.setup, "_zelkor_httpx_patched", False):
        _orig_otel_setup = OpenTelemetryProvider.setup

        def _wrap_pregel_current_span(provider) -> None:
            from langgraph.pregel import Pregel
            from opentelemetry import trace

            if getattr(Pregel, "_zelkor_run_span_wrapped", False):
                return
            tracer = trace.get_tracer("zelkor.aegra", tracer_provider=provider)

            def _span_name(graph) -> str:
                return str(getattr(graph, "name", None) or "LangGraph")

            orig_invoke = Pregel.invoke
            orig_ainvoke = Pregel.ainvoke
            orig_stream = Pregel.stream
            orig_astream = Pregel.astream
            orig_astream_events = Pregel.astream_events

            def invoke(self, *args, **kwargs):
                with tracer.start_as_current_span(_span_name(self)):
                    return orig_invoke(self, *args, **kwargs)

            async def ainvoke(self, *args, **kwargs):
                with tracer.start_as_current_span(_span_name(self)):
                    return await orig_ainvoke(self, *args, **kwargs)

            def stream(self, *args, **kwargs):
                with tracer.start_as_current_span(_span_name(self)):
                    yield from orig_stream(self, *args, **kwargs)

            async def astream(self, *args, **kwargs):
                with tracer.start_as_current_span(_span_name(self)):
                    async for item in orig_astream(self, *args, **kwargs):
                        yield item

            async def astream_events(self, *args, **kwargs):
                with tracer.start_as_current_span(_span_name(self)):
                    async for item in orig_astream_events(self, *args, **kwargs):
                        yield item

            Pregel.invoke = invoke  # type: ignore[method-assign]
            Pregel.ainvoke = ainvoke  # type: ignore[method-assign]
            Pregel.stream = stream  # type: ignore[method-assign]
            Pregel.astream = astream  # type: ignore[method-assign]
            Pregel.astream_events = astream_events  # type: ignore[method-assign]
            Pregel._zelkor_run_span_wrapped = True  # type: ignore[attr-defined]

        def _wrap_chat_openai_current_span(provider) -> None:
            from langchain_openai.chat_models.base import BaseChatOpenAI
            from opentelemetry import trace

            if getattr(BaseChatOpenAI, "_zelkor_current_span_wrapped", False):
                return
            tracer = trace.get_tracer("zelkor.aegra", tracer_provider=provider)
            orig_generate = BaseChatOpenAI._generate
            orig_agenerate = BaseChatOpenAI._agenerate

            def _generate(self, *args, **kwargs):
                with tracer.start_as_current_span("ChatOpenAI.request"):
                    return orig_generate(self, *args, **kwargs)

            async def _agenerate(self, *args, **kwargs):
                with tracer.start_as_current_span("ChatOpenAI.request"):
                    return await orig_agenerate(self, *args, **kwargs)

            BaseChatOpenAI._generate = _generate  # type: ignore[method-assign]
            BaseChatOpenAI._agenerate = _agenerate  # type: ignore[method-assign]
            BaseChatOpenAI._zelkor_current_span_wrapped = True  # type: ignore[attr-defined]

        def _otel_setup(self):
            _orig_otel_setup(self)
            provider = getattr(self, "_tracer_provider", None)
            if provider is None:
                return
            try:
                _wrap_pregel_current_span(provider)
            except Exception:
                _log.exception("Pregel current-span wrap failed")
            try:
                _wrap_chat_openai_current_span(provider)
            except Exception:
                _log.exception("ChatOpenAI current-span wrap failed")

        _otel_setup._zelkor_httpx_patched = True  # type: ignore[attr-defined]
        OpenTelemetryProvider.setup = _otel_setup  # type: ignore[method-assign]
except Exception:
    _log.exception("OpenTelemetryProvider httpx wrap failed")

if os.getenv("MCP_INJECT_ENABLED", "").strip().lower() in ("1", "true", "yes", "on"):
    from mcp_inject import patch_langgraph, write_inject_status

    try:
        patch_langgraph()
        write_inject_status("ok")
    except Exception:
        write_inject_status("failed")
        _log.exception("Mode B MCP inject failed")
        # site.py swallows sitecustomize exceptions; exit so the pod is not ready.
        os._exit(1)

try:
    from fastapi import FastAPI
    from starlette.responses import JSONResponse

    from mcp_inject import inject_ready

    _orig_fastapi_init = FastAPI.__init__

    def _fastapi_init(self, *args, **kwargs):
        _orig_fastapi_init(self, *args, **kwargs)

        async def _ready_gate(request, call_next):
            path = request.url.path
            if path == "/ready" or path.startswith("/ready/"):
                if not inject_ready():
                    return JSONResponse({"error": "mcp inject not ready"}, status_code=503)
            return await call_next(request)

        self.middleware("http")(_ready_gate)

    FastAPI.__init__ = _fastapi_init  # type: ignore[method-assign]
except Exception:
    _log.exception("ready gate install failed")
