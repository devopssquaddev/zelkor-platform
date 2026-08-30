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
from langchain_mcp_adapters.client import MultiServerMCPClient

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


def _current_run_config() -> dict:
    try:
        from langgraph.config import get_config

        cfg = get_config()
        if isinstance(cfg, dict):
            return cfg
    except Exception:
        pass
    try:
        from langchain_core.runnables.config import ensure_config

        cfg = ensure_config()
        if isinstance(cfg, dict):
            return cfg
    except Exception:
        pass
    return {}


def tenant_from_run_config(config: Optional[dict] = None) -> str:
    """Tenant identity for this tools/call. Never reads ZELKOR_TENANT_ID env."""
    cfg = config if isinstance(config, dict) else _current_run_config()
    configurable = cfg.get("configurable") if isinstance(cfg.get("configurable"), dict) else {}
    user = configurable.get("langgraph_auth_user") or configurable.get("user") or {}
    if isinstance(user, dict):
        for key in ("tenant_id", "identity"):
            value = user.get(key)
            if value:
                return str(value)
    for key in ("tenant_id", "identity"):
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


def _load_adapter_tools():
    url = _mcp_url()
    if not url:
        return []

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
        return await client.get_tools()

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
    if not _patch_factory(("deepagents", "deepagents.graph"), "create_deep_agent", extra):
        logger.info("Mode B: deepagents.create_deep_agent not installed (optional)")

    logger.info("Mode B: injected %s MCP tools", len(extra))
