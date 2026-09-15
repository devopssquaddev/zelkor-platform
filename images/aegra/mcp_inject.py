"""Mode B: bind MCP gateway tools onto compiled LangGraph / LangChain agents at load.

Enabled when MCP_INJECT_ENABLED is true. tools/list does not require tenant;
each tools/call uses wrap identity from Aegra langgraph_auth_user
(Authorization + X-Tenant-ID), not process env, client user_id, or traces.

langchain-mcp-adapters is a required pin (images/aegra/requirements.txt).
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import os
from pathlib import Path
from typing import Dict, Optional

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
    return os.getenv("MCP_URL", "").rstrip("/")


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
    """Tenant identity for this tools/call.

    Only Aegra langgraph_auth_user (passed config, Pregel ContextVar, or
    get_config()). Never ZELKOR_TENANT_ID, client user_id, or tool args.
    """
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


def inbound_authorization(config: Optional[dict] = None) -> str:
    """Inbound client Bearer from langgraph_auth_user.authorization (no mint)."""
    if isinstance(config, dict):
        from_cfg = authorization_from_auth_user(auth_user_from_config(config))
        if from_cfg:
            return from_cfg
    bound = current_auth_authorization()
    if bound:
        return bound
    if config is None:
        return authorization_from_auth_user(auth_user_from_config(_current_run_config()))
    return ""


def identity_headers(config: Optional[dict] = None) -> Dict[str, str]:
    headers = {"Content-Type": "application/json"}
    tenant = tenant_from_run_config(config)
    prefix = os.getenv("AUTH_DEV_TOKEN_PREFIX", "").strip()
    inbound = inbound_authorization(config)
    if tenant:
        headers["X-Tenant-ID"] = tenant
        if inbound:
            headers["Authorization"] = inbound
        elif prefix:
            headers["Authorization"] = f"Bearer {prefix}{tenant}"
        else:
            token = os.getenv("OPENAI_API_KEY") or os.getenv("AI_GATEWAY_API_KEY") or ""
            if token:
                headers["Authorization"] = f"Bearer {token}"
    return headers


class TenantRunAuth(httpx.Auth):
    """httpx.Auth that stamps wrap identity from the current LangGraph run."""

    def auth_flow(self, request):
        for key, value in identity_headers().items():
            if key.lower() == "content-type":
                continue
            request.headers[key] = value
        yield request


def _stamp_tenant_kwargs(kwargs: dict) -> dict:
    """Overwrite tenant_id from wrap identity so the model cannot invent one."""
    tenant = tenant_from_run_config()
    if not tenant:
        return kwargs
    stamped = dict(kwargs)
    stamped["tenant_id"] = tenant
    return stamped


def _tool_error_text(exc: BaseException) -> str:
    return f"Error: {type(exc).__name__}: {exc}"


def _normalize_tool_result(tool, value):
    """langchain-mcp-adapters uses response_format=content_and_artifact."""
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


def _stamp_invoke_args(args: tuple, kwargs: dict) -> tuple[tuple, dict]:
    if args and isinstance(args[0], dict):
        args = (_stamp_tenant_kwargs(args[0]),) + args[1:]
    return args, _stamp_tenant_kwargs(kwargs)


def _stamp_tenant_on_tool(tool):
    orig_coro = getattr(tool, "coroutine", None)
    orig_func = getattr(tool, "func", None)
    updates = {}
    if orig_coro is not None:

        async def coro(*args, **kwargs):
            args, kwargs = _stamp_invoke_args(args, kwargs)
            try:
                result = _normalize_tool_result(tool, await orig_coro(*args, **kwargs))
                result = _maybe_stamp_sandbox_tool(tool, result)
                logger.debug("MCP tool %s ok", getattr(tool, "name", "?"))
                return result
            except Exception as exc:
                logger.warning("MCP tool %s failed: %s", getattr(tool, "name", "?"), exc)
                return _normalize_tool_result(tool, _tool_error_text(exc))

        updates["coroutine"] = coro
    if orig_func is not None:

        def func(*args, **kwargs):
            args, kwargs = _stamp_invoke_args(args, kwargs)
            try:
                result = _normalize_tool_result(tool, orig_func(*args, **kwargs))
                result = _maybe_stamp_sandbox_tool(tool, result)
                logger.debug("MCP tool %s ok", getattr(tool, "name", "?"))
                return result
            except Exception as exc:
                logger.warning("MCP tool %s failed: %s", getattr(tool, "name", "?"), exc)
                return _normalize_tool_result(tool, _tool_error_text(exc))

        updates["func"] = func
    if not updates:
        return tool
    if getattr(tool, "handle_tool_error", None) in (None, False):
        updates["handle_tool_error"] = True
    return tool.model_copy(update=updates)


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


def filter_tools_by_prefix(tools, prefixes: tuple[str, ...]):
    if not prefixes:
        return list(tools or [])
    allowed = []
    for tool in tools or []:
        name = getattr(tool, "name", "") or ""
        if any(name.startswith(f"{prefix}__") for prefix in prefixes):
            allowed.append(tool)
    return allowed


def _caller_module_prefixes() -> tuple[str, ...]:
    import inspect

    skip = {
        "mcp_inject",
        "langchain.agents",
        "langchain.agents.factory",
    }
    for frame_info in inspect.stack()[1:]:
        mod = inspect.getmodule(frame_info.frame)
        if mod is None:
            continue
        name = getattr(mod, "__name__", "") or ""
        if name in skip or name.startswith(("langchain.", "langgraph.", "langchain_core.")):
            continue
        if getattr(mod, "MCP_INJECT_PREFIXES", None) is not None:
            return _prefixes_from_module(mod)
        return _inject_prefixes()
    return _inject_prefixes()


def _tools_for_caller(extra):
    prefixes = _caller_module_prefixes()
    filtered = filter_tools_by_prefix(extra, prefixes)
    if prefixes:
        logger.debug(
            "Mode B: caller prefixes %s -> %s tools",
            ",".join(prefixes),
            len(filtered),
        )
    return filtered



def _run_coro_sync(coro):
    """Run a coroutine from sync code, including during uvicorn lifespan."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def _load_adapter_tools():
    url = _mcp_url()
    if not url:
        return []

    from langchain_mcp_adapters.client import MultiServerMCPClient

    async def _get():
        client = MultiServerMCPClient(
            {
                "zelkor": {
                    "transport": "http",
                    "url": f"{url}/mcp",
                    "auth": TenantRunAuth(),
                }
            }
        )
        return [_stamp_tenant_on_tool(tool) for tool in await client.get_tools()]

    return list(_run_coro_sync(_get()))


def _merge_tools(existing, extra):
    merged = list(existing or []) + list(extra or [])
    return merged


def _wrap_agent_factory(orig, extra):
    def wrapped(*args, **kwargs):
        inject = _tools_for_caller(extra)
        if "tools" in kwargs:
            kwargs["tools"] = _merge_tools(kwargs.get("tools"), inject)
        elif len(args) >= 2:
            args = (args[0], _merge_tools(args[1], inject), *args[2:])
        else:
            kwargs["tools"] = list(inject)
        return orig(*args, **kwargs)

    return wrapped


def _patch_factory(module_names: tuple[str, ...], attr: str, extra) -> bool:
    """Replace attr on each imported module so `from pkg.sub import fn` sees the wrap."""
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
            wrapped = _wrap_agent_factory(orig, extra)
        setattr(module, attr, wrapped)
        patched = True
    return patched


def _patch_toolnode(extra) -> None:
    import importlib

    for name in ("langgraph.prebuilt", "langgraph.prebuilt.tool_node"):
        try:
            module = importlib.import_module(name)
        except ImportError:
            continue
        tool_node = getattr(module, "ToolNode", None)
        if tool_node is None or getattr(tool_node, "_zelkor_mcp_patched", False):
            continue
        orig_init = tool_node.__init__

        def _toolnode_init(self, tools, *args, _orig=orig_init, **kwargs):
            _orig(self, _merge_tools(tools, _tools_for_caller(extra)), *args, **kwargs)

        tool_node.__init__ = _toolnode_init  # type: ignore[method-assign]
        tool_node._zelkor_mcp_patched = True  # type: ignore[attr-defined]


def patch_langgraph() -> None:
    extra = _load_adapter_tools()
    if extra is None:
        extra = []
    if not extra:
        logger.info("Mode B: no MCP tools to inject")

    _patch_toolnode(extra)
    if not _patch_factory(("langchain.agents", "langchain.agents.factory"), "create_agent", extra):
        logger.info("Mode B: langchain.agents.create_agent not available")
    _patch_factory(
        ("langgraph.prebuilt", "langgraph.prebuilt.chat_agent_executor"),
        "create_react_agent",
        extra,
    )

    logger.info("Mode B: injected %s MCP tools", len(extra))
