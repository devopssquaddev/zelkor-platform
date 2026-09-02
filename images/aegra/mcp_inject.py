"""Mode B: bind MCP gateway tools onto compiled LangGraph / LangChain agents at load.

Enabled when MCP_INJECT_ENABLED is true. tools/list does not require tenant;
each tools/call uses wrap identity from the current LangGraph run config
(Authorization + X-Tenant-ID), not process env.

langchain-mcp-adapters is a required pin (images/aegra/requirements.txt).
"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Dict, Optional

import httpx

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
    configurable = cfg.get("configurable") if isinstance(cfg.get("configurable"), dict) else {}
    return bool(
        configurable.get("langgraph_auth_user")
        or configurable.get("user")
        or configurable.get("user_id")
        or configurable.get("tenant_id")
        or configurable.get("identity")
    )


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


def _identity_from_user(user) -> str:
    if user is None:
        return ""
    if isinstance(user, dict):
        for key in ("tenant_id", "identity"):
            value = user.get(key)
            if value:
                return str(value)
        return ""
    for key in ("tenant_id", "identity"):
        value = getattr(user, key, None)
        if value:
            return str(value)
    try:
        for key in ("tenant_id", "identity"):
            value = user[key]  # type: ignore[index]
            if value:
                return str(value)
    except Exception:
        pass
    return ""


def tenant_from_run_config(config: Optional[dict] = None) -> str:
    """Tenant identity for this tools/call. Never reads ZELKOR_TENANT_ID env."""
    cfg = config if isinstance(config, dict) else _current_run_config()
    configurable = cfg.get("configurable") if isinstance(cfg.get("configurable"), dict) else {}
    from_user = _identity_from_user(
        configurable.get("langgraph_auth_user") or configurable.get("user")
    )
    if from_user:
        return from_user
    for key in ("tenant_id", "identity", "user_id"):
        value = configurable.get(key)
        if value and not isinstance(value, dict):
            return str(value)
    return ""


def identity_headers(config: Optional[dict] = None) -> Dict[str, str]:
    headers = {"Content-Type": "application/json"}
    tenant = tenant_from_run_config(config)
    prefix = os.getenv("AUTH_DEV_TOKEN_PREFIX", "").strip()
    if tenant:
        headers["X-Tenant-ID"] = tenant
        if prefix:
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

    try:
        return list(asyncio.run(_get()))
    except RuntimeError as exc:
        if "asyncio.run() cannot be called from a running event loop" not in str(exc):
            raise
        loop = asyncio.new_event_loop()
        try:
            return list(loop.run_until_complete(_get()))
        finally:
            loop.close()


def _merge_tools(existing, extra):
    merged = list(existing or []) + list(extra or [])
    return merged


def _wrap_agent_factory(orig, extra):
    def wrapped(*args, **kwargs):
        if "tools" in kwargs:
            kwargs["tools"] = _merge_tools(kwargs.get("tools"), extra)
        elif len(args) >= 2:
            args = (args[0], _merge_tools(args[1], extra), *args[2:])
        else:
            kwargs["tools"] = list(extra)
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
            _orig(self, _merge_tools(tools, extra), *args, **kwargs)

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
