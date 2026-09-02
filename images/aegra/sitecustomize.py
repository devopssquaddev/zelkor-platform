"""Auto-loaded wrap: auth.path inject, Mode B MCP inject, Langfuse run trace."""
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

try:
    from trace_wrap import attach_langfuse_project_baggage, patch_http_clients, patch_otel_setup

    attach_langfuse_project_baggage()
    patch_http_clients()
    patch_otel_setup()
except Exception:
    _log.exception("trace wrap (Pregel root / ChatOpenAI.request / traceparent) failed")

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
