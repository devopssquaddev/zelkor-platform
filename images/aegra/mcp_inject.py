"""Mode B: per-run MCP tools via LangGraph factory (07_clients §2).

Module-level ``create_agent`` / ``create_react_agent`` return a 2-parameter factory.
MCP ``streamable_http`` opens only for ``threads.create_run``.
"""
from __future__ import annotations

import asyncio
import contextlib
import contextvars
import inspect
import itertools
import json
import logging
import os
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Dict, Optional, Sequence, Tuple

import httpx

from wrap_identity import (
    auth_user_from_config,
    authorization_from_auth_user,
    current_auth_authorization,
    current_auth_identity,
    identity_from_auth_user,
)

logger = logging.getLogger("zelkor-mcp-inject")

INJECT_STATUS_PATH = Path(os.getenv("MCP_INJECT_STATUS_PATH", "/tmp/zelkor-mcp-inject.status"))

_SPEC_CACHE_TTL_SEC = 60.0
# cache_key -> (monotonic_ts, list of mcp.types.Tool)
_TOOL_SPEC_CACHE: dict[str, tuple[float, list[Any]]] = {}
_RUN_MCP: contextvars.ContextVar[Optional[dict[str, Any]]] = contextvars.ContextVar(
    "zelkor_mcp_run", default=None
)
_RPC_IDS = itertools.count(1)
_RPC_STATE: dict[str, Any] = {"sse_drops": 0}
_SSE_HOOKED = False
_HTTP_STATUS_RE = re.compile(r"\b(?:HTTP[ /]|status[=: ]+)(\d{3})\b", re.I)

try:
    from langchain_core.runnables import RunnableConfig
except ImportError:  # pragma: no cover
    RunnableConfig = dict  # type: ignore[misc,assignment]

try:
    from langgraph_sdk.runtime import ServerRuntime
except ImportError:  # pragma: no cover
    ServerRuntime = Any  # type: ignore[misc,assignment]


def inject_enabled() -> bool:
    return os.getenv("MCP_INJECT_ENABLED", "").strip().lower() in ("1", "true", "yes", "on")


def write_inject_status(status: str) -> None:
    INJECT_STATUS_PATH.write_text(status.strip() + "\n", encoding="utf-8")


def read_inject_status() -> str:
    try:
        return INJECT_STATUS_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def inject_ready() -> bool:
    if not inject_enabled():
        return True
    return read_inject_status() == "ok"


def _mcp_url() -> str:
    base = os.getenv("MCP_URL", "").rstrip("/")
    if not base:
        return ""
    if base.endswith("/mcp"):
        return base
    return f"{base}/mcp"


def _config_has_identity(cfg: dict) -> bool:
    return auth_user_from_config(cfg) is not None


def _current_run_config() -> dict:
    candidates: list[dict] = []
    try:
        from langgraph.config import get_config

        cfg = get_config()
        if isinstance(cfg, dict):
            candidates.append(cfg)
    except Exception:
        pass
    try:
        from langchain_core.runnables.config import ensure_config

        cfg = ensure_config()
        if isinstance(cfg, dict):
            candidates.append(cfg)
    except Exception:
        pass
    for cfg in candidates:
        if _config_has_identity(cfg):
            return cfg
    return candidates[0] if candidates else {}


def tenant_from_run_config(config: Optional[dict] = None) -> str:
    """Tenant identity from langgraph_auth_user only (cache key / logging)."""
    if isinstance(config, dict):
        from_cfg = identity_from_auth_user(auth_user_from_config(config))
        if from_cfg:
            return from_cfg
    bound = current_auth_identity()
    if bound:
        return bound
    if config is None:
        return identity_from_auth_user(auth_user_from_config(_current_run_config()))
    return ""


def _bootstrap_mcp_authorization() -> str:
    raw = os.getenv("MCP_AUTH_TOKEN", "").strip()
    if not raw:
        return ""
    if raw.lower().startswith("bearer "):
        return raw
    return f"Bearer {raw}"


def identity_headers(config: Optional[dict] = None) -> Dict[str, str]:
    """HTTP headers for legacy callers (Authorization only; no X-Tenant-ID)."""
    headers = {"Content-Type": "application/json"}
    inbound = inbound_authorization(config)
    if inbound:
        headers["Authorization"] = inbound
    return headers


def inbound_authorization(config: Optional[dict] = None) -> str:
    """Bearer for MCP: langgraph_auth_user.authorization, else MCP_AUTH_TOKEN service token."""
    if isinstance(config, dict):
        from_cfg = authorization_from_auth_user(auth_user_from_config(config))
        if from_cfg:
            return from_cfg
    bound = current_auth_authorization()
    if bound:
        return bound
    if config is None:
        from_cfg = authorization_from_auth_user(auth_user_from_config(_current_run_config()))
        if from_cfg:
            return from_cfg
        return _bootstrap_mcp_authorization()
    return _bootstrap_mcp_authorization()


def _parse_prefixes(value: str) -> tuple[str, ...]:
    if not value or not str(value).strip():
        return ()
    return tuple(part.strip() for part in str(value).split(",") if part.strip())


def _inject_prefixes() -> tuple[str, ...]:
    return _parse_prefixes(os.getenv("MCP_INJECT_TOOL_PREFIXES", ""))


def _prefixes_from_module(mod) -> tuple[str, ...]:
    raw = getattr(mod, "MCP_INJECT_PREFIXES", None)
    if raw is None:
        return _inject_prefixes()
    if isinstance(raw, str):
        return _parse_prefixes(raw)
    return tuple(str(part).strip() for part in raw if str(part).strip())


def _tools_from_module(mod) -> tuple[str, ...]:
    raw = getattr(mod, "MCP_INJECT_TOOLS", None)
    if raw is None:
        return ()
    if isinstance(raw, str):
        text = raw.strip()
        return (text,) if text else ()
    return tuple(str(part).strip() for part in raw if str(part).strip())


def filter_tools_by_prefix(tools, prefixes: tuple[str, ...]):
    if not prefixes:
        return list(tools or [])
    allowed = []
    for tool in tools or []:
        name = getattr(tool, "name", "") or ""
        if any(name.startswith(f"{prefix}__") for prefix in prefixes):
            allowed.append(tool)
    return allowed


def _filter_specs_by_prefix(specs: Sequence[Any], prefixes: tuple[str, ...]) -> list[Any]:
    if not prefixes:
        return list(specs)
    out = []
    for spec in specs:
        name = getattr(spec, "name", "") or ""
        if any(name.startswith(f"{prefix}__") for prefix in prefixes):
            out.append(spec)
    return out


def _filter_specs_by_names(specs: Sequence[Any], names: tuple[str, ...]) -> list[Any]:
    if not names:
        return list(specs)
    wanted = set(names)
    return [spec for spec in specs if getattr(spec, "name", "") in wanted]


def _select_specs(
    specs: Sequence[Any],
    prefixes: tuple[str, ...],
    inject_tools: tuple[str, ...],
) -> list[Any]:
    if inject_tools:
        return _filter_specs_by_names(specs, inject_tools)
    return _filter_specs_by_prefix(specs, prefixes)


def _caller_agent_module():
    skip = {
        "mcp_inject",
        "langchain.agents",
        "langchain.agents.factory",
        "langgraph.prebuilt",
        "langgraph.prebuilt.chat_agent_executor",
    }
    for frame_info in inspect.stack()[2:]:
        mod = inspect.getmodule(frame_info.frame)
        if mod is None:
            continue
        name = getattr(mod, "__name__", "") or ""
        if name in skip or name.startswith(("langchain.", "langgraph.", "langchain_core.")):
            continue
        return mod
    return None


def _is_module_level_create_agent_call() -> bool:
    """True when ``create_agent`` is invoked at module import (Mode B).

    Skip ``mcp_inject`` frames so the helper itself is not mistaken for the
    caller (``stack()[1]`` is ``wrapped``, never ``<module>``).
    """
    skip = {"mcp_inject"}
    for frame_info in inspect.stack()[1:]:
        mod = inspect.getmodule(frame_info.frame)
        name = getattr(mod, "__name__", "") or ""
        if name in skip or name.endswith(".mcp_inject"):
            continue
        return frame_info.frame.f_code.co_name == "<module>"
    return False


def _cache_key(config: Optional[dict]) -> str:
    tenant = tenant_from_run_config(config)
    if tenant:
        return tenant
    auth = inbound_authorization(config)
    return auth or "__anonymous__"


def _cached_specs(config: Optional[dict]) -> list[Any]:
    key = _cache_key(config)
    entry = _TOOL_SPEC_CACHE.get(key)
    if not entry:
        return []
    if time.monotonic() - entry[0] > _SPEC_CACHE_TTL_SEC:
        return []
    return list(entry[1])


def _store_specs(config: Optional[dict], specs: list[Any]) -> None:
    _TOOL_SPEC_CACHE[_cache_key(config)] = (time.monotonic(), list(specs))


def _merge_tools(existing, extra):
    return list(existing or []) + list(extra or [])


def _compile_agent(orig: Callable, args: tuple, kwargs: dict, mcp_tools: list[Any]) -> Any:
    kw = dict(kwargs)
    arg_list = list(args)
    if mcp_tools:
        if "tools" in kw:
            kw["tools"] = _merge_tools(kw.get("tools"), mcp_tools)
        elif len(arg_list) >= 2:
            arg_list[1] = _merge_tools(arg_list[1], mcp_tools)
        else:
            kw["tools"] = list(mcp_tools)
    return orig(*arg_list, **kw)


def _tool_error_text(exc: BaseException) -> str:
    return f"Error: {type(exc).__name__}: {exc}"


def _tool_timeout_sec() -> float:
    raw = os.getenv("ZELKOR_MCP_TOOL_TIMEOUT_SEC", "600").strip()
    try:
        val = float(raw)
    except ValueError:
        return 600.0
    if val <= 0:
        return 600.0
    return val


def _rpc_debug(phase: str, **fields: Any) -> None:
    extra = {"event": "mcp_rpc", "phase": phase}
    extra.update({k: v for k, v in fields.items() if v is not None and v != ""})
    logger.debug("mcp rpc %s", phase, extra=extra)


class _SseDropHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = record.getMessage()
        except Exception:
            return
        low = msg.lower()
        if "disconnect" not in low and "reconnect" not in low:
            return
        _RPC_STATE["sse_drops"] = int(_RPC_STATE.get("sse_drops") or 0) + 1
        status = None
        match = _HTTP_STATUS_RE.search(msg)
        if match:
            status = int(match.group(1))
        exc_type = ""
        if record.exc_info and record.exc_info[0]:
            exc_type = record.exc_info[0].__name__
        _rpc_debug("sse_drop", exc_type=exc_type, status=status)


def _ensure_sse_drop_hook() -> None:
    global _SSE_HOOKED
    if _SSE_HOOKED:
        return
    handler = _SseDropHandler()
    handler.setLevel(logging.DEBUG)
    for name in ("mcp.client.streamable_http", "mcp.client.sse", "httpx", "httpcore"):
        log = logging.getLogger(name)
        log.addHandler(handler)
    _SSE_HOOKED = True


async def _session_call_tool(session: Any, name: str, arguments: Optional[dict[str, Any]]) -> Any:
    _ensure_sse_drop_hook()
    rpc_id = next(_RPC_IDS)
    t0 = time.monotonic()
    _rpc_debug("send", tool=name, id=rpc_id)

    async def _heartbeat() -> None:
        while True:
            await asyncio.sleep(30)
            _rpc_debug(
                "wait",
                tool=name,
                pending_id=rpc_id,
                since_send_s=int(time.monotonic() - t0),
                sse_drops=int(_RPC_STATE.get("sse_drops") or 0),
            )

    beat = asyncio.create_task(_heartbeat())
    try:
        result = await asyncio.wait_for(
            session.call_tool(name, arguments or {}),
            timeout=_tool_timeout_sec(),
        )
        _rpc_debug(
            "recv",
            tool=name,
            id=rpc_id,
            is_error=bool(getattr(result, "isError", False)),
        )
        return result
    except TimeoutError as exc:
        _rpc_debug("recv", tool=name, id=rpc_id, is_error=True, exc_type=type(exc).__name__)
        raise
    finally:
        beat.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await beat


def _normalize_tool_result(tool, value):
    if getattr(tool, "response_format", None) == "content_and_artifact":
        if isinstance(value, tuple) and len(value) == 2:
            return value
        return (value, None)
    return value


def _maybe_stamp_sandbox_tool(tool, result):
    name = getattr(tool, "name", "") or ""
    if name != "sandbox__execute_python":
        return result
    try:
        from sandbox_trace import stamp_sandbox_execution_span

        payload = result
        if isinstance(result, tuple) and result:
            payload = result[0]
        stamp_sandbox_execution_span(payload)
    except Exception:
        logger.debug("sandbox trace stamp skipped for %s", name, exc_info=True)
    return result


def _is_tool_not_found(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "not found" in text or "unknown tool" in text


def _wrap_session_tool_with_reinit(tool, session_holder: dict[str, Any]):
    """Re-initialize MCP session once on tool-not-found, then surface isError."""
    orig_coro = getattr(tool, "coroutine", None)
    orig_func = getattr(tool, "func", None)
    updates: dict[str, Any] = {}

    async def _retry_call(real_coro, *args, **kwargs):
        try:
            return await real_coro(*args, **kwargs)
        except Exception as exc:
            if not _is_tool_not_found(exc) or session_holder.get("reinitialized"):
                raise
            session = session_holder.get("session")
            if session is None:
                raise
            session_holder["reinitialized"] = True
            await session.initialize()
            return await real_coro(*args, **kwargs)

    if orig_coro is not None:

        async def coro(*args, **kwargs):
            try:
                result = _normalize_tool_result(tool, await _retry_call(orig_coro, *args, **kwargs))
                return _maybe_stamp_sandbox_tool(tool, result)
            except Exception as exc:
                logger.warning("MCP tool %s failed: %s", getattr(tool, "name", "?"), exc)
                return _normalize_tool_result(tool, _tool_error_text(exc))

        updates["coroutine"] = coro

    if orig_func is not None:

        def func(*args, **kwargs):
            try:
                result = _normalize_tool_result(tool, orig_func(*args, **kwargs))
                return _maybe_stamp_sandbox_tool(tool, result)
            except Exception as exc:
                logger.warning("MCP tool %s failed: %s", getattr(tool, "name", "?"), exc)
                return _normalize_tool_result(tool, _tool_error_text(exc))

        updates["func"] = func

    if not updates:
        return tool
    if getattr(tool, "handle_tool_error", None) in (None, False):
        updates["handle_tool_error"] = True
    return tool.model_copy(update=updates)


def _build_session_tools(
    session,
    specs: Sequence[Any],
    prefixes: tuple[str, ...],
    inject_tools: tuple[str, ...],
    session_holder: dict[str, Any],
) -> list[Any]:
    from langchain_mcp_adapters.tools import convert_mcp_tool_to_langchain_tool

    selected = _select_specs(specs, prefixes, inject_tools)
    tools = []
    for spec in selected:
        tool = convert_mcp_tool_to_langchain_tool(session, spec)
        tools.append(_wrap_session_tool_with_reinit(tool, session_holder))
    return tools


def _placeholder_stub_tool():
    from langchain_core.tools import BaseTool

    class _Placeholder(BaseTool):
        name: str = "_zelkor_mcp_unavailable"
        description: str = "MCP tools not loaded (no prior run for this tenant)"

        def _run(self, *args, **kwargs):
            raise RuntimeError("MCP tool unavailable without an active run session")

        async def _arun(self, *args, **kwargs):
            raise RuntimeError("MCP tool unavailable without an active run session")

    return _Placeholder()


def _stub_from_spec(spec: Any):
    from langchain_core.tools import StructuredTool

    name = getattr(spec, "name", "") or "_zelkor_mcp_stub"
    description = getattr(spec, "description", "") or f"MCP tool {name}"

    async def _araise(**_kwargs):
        raise RuntimeError(f"MCP session not open for tool {name}")

    return StructuredTool.from_function(
        coroutine=_araise,
        name=name,
        description=description,
    )


def _build_stub_tools(
    config: Optional[dict],
    prefixes: tuple[str, ...],
    inject_tools: tuple[str, ...],
) -> list[Any]:
    specs = _cached_specs(config)
    selected = _select_specs(specs, prefixes, inject_tools)
    if not selected:
        return [_placeholder_stub_tool()]
    return [_stub_from_spec(spec) for spec in selected]


@asynccontextmanager
async def _mcp_client_session(
    bearer: str,
) -> AsyncIterator[Any]:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    url = _mcp_url()
    if not url:
        raise RuntimeError("MCP_URL is not set")

    auth = bearer if bearer.lower().startswith("bearer ") else f"Bearer {bearer}"
    timeout = httpx.Timeout(120.0, connect=30.0)
    async with httpx.AsyncClient(
        headers={"Authorization": auth},
        timeout=timeout,
    ) as http_client:
        async with streamable_http_client(url, http_client=http_client) as streams:
            read_stream, write_stream, _ = streams
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                yield session


def _span_arguments(arguments: Optional[dict[str, Any]]) -> str:
    safe: dict[str, Any] = {}
    for key, value in (arguments or {}).items():
        if key.lower() in {"authorization", "token", "secret", "password"}:
            continue
        if key == "text" and isinstance(value, str) and len(value) > 512:
            safe["text"] = value[:512] + "…"
            safe["text_bytes"] = len(value)
        else:
            safe[key] = value
    raw = json.dumps(safe, default=str)
    return raw if len(raw) <= 2048 else raw[:2048] + "…"


@contextlib.contextmanager
def _mcp_tool_span(name: str, arguments: Optional[dict[str, Any]]):
    """Child of the current run span. OpenInference does not see a raw tools/call."""
    try:
        from opentelemetry import trace
    except ImportError:
        yield None
        return
    tracer = trace.get_tracer("zelkor.mcp-inject")
    with tracer.start_as_current_span(name) as span:
        payload = _span_arguments(arguments)
        span.set_attribute("openinference.span.kind", "TOOL")
        span.set_attribute("tool.name", name)
        span.set_attribute("langfuse.observation.input", payload)
        span.set_attribute("input.value", payload)
        try:
            from trace_wrap import stamp_tool_span

            stamp_tool_span(span, known_tool=True)
        except Exception:
            pass
        yield span


def _finish_mcp_tool_span(span: Any, result: str) -> None:
    if span is None:
        return
    text = result if len(result) <= 2048 else result[:2048] + "…"
    span.set_attribute("langfuse.observation.output", text)
    span.set_attribute("output.value", text)
    if result.startswith("Error:"):
        from opentelemetry import trace

        span.set_status(trace.Status(trace.StatusCode.ERROR, "MCP tool failed"))


def _tool_result_text(result: Any) -> str:
    content = getattr(result, "content", None) or []
    texts = [i.text for i in content if getattr(i, "text", None)]
    if getattr(result, "isError", False):
        text = texts[0] if texts else "MCP tool call failed"
        if text.startswith("Error:"):
            return text
        return f"Error: {text}"
    return "\n".join(texts)


@asynccontextmanager
async def mcp_run_session() -> AsyncIterator[None]:
    """One MCP streamable-HTTP session for a Pregel run (same task enter/exit)."""
    if _RUN_MCP.get() is not None:
        yield
        return
    url = _mcp_url()
    bearer = inbound_authorization()
    if not url or not bearer:
        yield
        return
    async with _mcp_client_session(bearer) as session:
        token = _RUN_MCP.set({"session": session})
        try:
            yield
        finally:
            _RUN_MCP.reset(token)


async def call_tool(name: str, arguments: Optional[dict[str, Any]] = None) -> str:
    """tools/call on MCP_URL with inbound JWT. Failures return Error: text (do not abort the run)."""
    try:
        with _mcp_tool_span(name, arguments) as span:
            result = await _call_tool_unspanned(name, arguments)
            _finish_mcp_tool_span(span, result)
            return result
    except Exception as exc:
        return _tool_error_text(exc)


async def _call_tool_unspanned(name: str, arguments: Optional[dict[str, Any]]) -> str:
    holder = _RUN_MCP.get()
    if holder is not None and holder.get("session") is not None:
        result = await _session_call_tool(holder["session"], name, arguments)
        return _tool_result_text(result)
    if not _mcp_url():
        return _tool_error_text(RuntimeError("MCP_URL is not set"))
    bearer = inbound_authorization()
    if not bearer:
        return _tool_error_text(RuntimeError("no MCP bearer"))
    async with _mcp_client_session(bearer) as session:
        result = await _session_call_tool(session, name, arguments)
    return _tool_result_text(result)


def patch_pregel_mcp_session() -> None:
    try:
        from langgraph.pregel import Pregel
    except ImportError:
        return
    if getattr(Pregel, "_zelkor_mcp_run_session", False):
        return

    orig_ainvoke = Pregel.ainvoke
    orig_astream = Pregel.astream
    orig_astream_events = Pregel.astream_events

    async def ainvoke(self, *args, **kwargs):
        async with mcp_run_session():
            return await orig_ainvoke(self, *args, **kwargs)

    async def astream(self, *args, **kwargs):
        async with mcp_run_session():
            async for item in orig_astream(self, *args, **kwargs):
                yield item

    async def astream_events(self, *args, **kwargs):
        async with mcp_run_session():
            async for item in orig_astream_events(self, *args, **kwargs):
                yield item

    Pregel.ainvoke = ainvoke  # type: ignore[method-assign]
    Pregel.astream = astream  # type: ignore[method-assign]
    Pregel.astream_events = astream_events  # type: ignore[method-assign]
    Pregel._zelkor_mcp_run_session = True  # type: ignore[attr-defined]


async def _list_tools_cached(session, config: Optional[dict]) -> list[Any]:
    key = _cache_key(config)
    entry = _TOOL_SPEC_CACHE.get(key)
    now = time.monotonic()
    if entry and now - entry[0] <= _SPEC_CACHE_TTL_SEC:
        return list(entry[1])
    result = await session.list_tools()
    tools_attr = getattr(result, "tools", None)
    if tools_attr is not None:
        specs = list(tools_attr)
    elif isinstance(result, list):
        specs = list(result)
    else:
        specs = []
    _store_specs(config, specs)
    return specs


def _make_mode_b_graph_factory(
    orig: Callable,
    args: tuple,
    kwargs: dict,
    prefixes: tuple[str, ...],
    inject_tools: tuple[str, ...],
) -> Callable:
    def zelkor_mode_b_graph(config: RunnableConfig, runtime: ServerRuntime) -> Any:
        access = getattr(runtime, "access_context", "") or ""

        if access != "threads.create_run":
            stubs = _build_stub_tools(config, prefixes, inject_tools)
            return _compile_agent(orig, args, kwargs, stubs)

        bearer = inbound_authorization(config if isinstance(config, dict) else None)
        if not bearer:
            logger.warning(
                "Mode B: no MCP bearer for threads.create_run; graph runs without MCP tools"
            )
            return _compile_agent(orig, args, kwargs, [])

        @asynccontextmanager
        async def _run_session():
            async with _mcp_client_session(bearer) as session:
                session_holder: dict[str, Any] = {"session": session, "reinitialized": False}
                specs = await _list_tools_cached(session, config if isinstance(config, dict) else None)
                tools = _build_session_tools(
                    session,
                    specs,
                    prefixes,
                    inject_tools,
                    session_holder,
                )
                yield _compile_agent(orig, args, kwargs, tools)

        return _run_session()

    zelkor_mode_b_graph.__name__ = "zelkor_mode_b_graph"
    zelkor_mode_b_graph.__annotations__ = {
        "config": RunnableConfig,
        "runtime": ServerRuntime,
    }
    return zelkor_mode_b_graph


def _wrap_agent_factory(orig: Callable) -> Callable:
    def wrapped(*args, **kwargs):
        if not _is_module_level_create_agent_call():
            return orig(*args, **kwargs)
        mod = _caller_agent_module()
        prefixes = _prefixes_from_module(mod) if mod is not None else _inject_prefixes()
        inject_tools = _tools_from_module(mod) if mod is not None else ()
        return _make_mode_b_graph_factory(orig, args, kwargs, prefixes, inject_tools)

    wrapped.__name__ = getattr(orig, "__name__", "create_agent")
    wrapped.__doc__ = getattr(orig, "__doc__", None)
    return wrapped


@asynccontextmanager
async def zelkor_mcp_tools(
    config: RunnableConfig,
    *,
    names: Sequence[str] = (),
    prefixes: Sequence[str] = (),
) -> AsyncIterator[list[Any]]:
    """Open a per-run MCP session and yield LangChain tools (explicit factories)."""
    prefix_tuple = tuple(str(p).strip() for p in prefixes if str(p).strip())
    if not prefix_tuple:
        prefix_tuple = _inject_prefixes()
    name_tuple = tuple(str(n).strip() for n in names if str(n).strip())

    bearer = inbound_authorization(config if isinstance(config, dict) else None)
    if not bearer:
        logger.warning("zelkor_mcp_tools: no MCP bearer; returning no tools")
        yield []
        return

    async with _mcp_client_session(bearer) as session:
        session_holder: dict[str, Any] = {"session": session, "reinitialized": False}
        specs = await _list_tools_cached(session, config if isinstance(config, dict) else None)
        yield _build_session_tools(session, specs, prefix_tuple, name_tuple, session_holder)


def _patch_factory(module_names: tuple[str, ...], attr: str) -> bool:
    import importlib

    wrapped = None
    patched = False
    for name in module_names:
        try:
            module = importlib.import_module(name)
        except ImportError:
            continue
        orig = getattr(module, attr, None)
        if orig is None:
            continue
        if wrapped is None:
            wrapped = _wrap_agent_factory(orig)
        setattr(module, attr, wrapped)
        patched = True
    return patched


def patch_langgraph() -> None:
    if not _patch_factory(("langchain.agents", "langchain.agents.factory"), "create_agent"):
        logger.info("Mode B: langchain.agents.create_agent not available")
    _patch_factory(
        ("langgraph.prebuilt", "langgraph.prebuilt.chat_agent_executor"),
        "create_react_agent",
    )
    patch_pregel_mcp_session()
    logger.info("Mode B: per-run factory patch installed")
