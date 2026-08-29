"""Mode B: bind MCP gateway tools onto compiled LangGraph graphs at load.

Enabled when MCP_INJECT_ENABLED is true. tools/list does not require tenant;
each tools/call uses wrap identity (Authorization + X-Tenant-ID).
"""
from __future__ import annotations

import json
import logging
import os
import urllib.request
from typing import Any, Dict, List, Optional

logger = logging.getLogger("zelkor-mcp-inject")


def inject_enabled() -> bool:
    return os.getenv("MCP_INJECT_ENABLED", "").strip().lower() in ("1", "true", "yes", "on")


def _mcp_url() -> str:
    return os.getenv("MCP_URL", "").rstrip("/")


def _identity_headers() -> Dict[str, str]:
    headers = {"Content-Type": "application/json"}
    token = os.getenv("OPENAI_API_KEY") or os.getenv("AI_GATEWAY_API_KEY") or ""
    tenant = os.getenv("ZELKOR_TENANT_ID", "")
    prefix = os.getenv("AUTH_DEV_TOKEN_PREFIX", "").strip()
    if tenant:
        headers["X-Tenant-ID"] = tenant
        if prefix:
            headers["Authorization"] = f"Bearer {prefix}{tenant}"
    elif token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _rpc(method: str, params: dict, headers: Optional[Dict[str, str]] = None) -> Any:
    url = _mcp_url()
    if not url:
        return None
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode("utf-8")
    hdrs = {"Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(f"{url}/mcp", data=payload, headers=hdrs, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if "error" in data:
        raise RuntimeError(data["error"].get("message", str(data["error"])))
    return data.get("result")


def list_mcp_tools() -> List[Dict[str, Any]]:
    result = _rpc("tools/list", {}, {"Content-Type": "application/json"})
    if not result:
        return []
    return result.get("tools") or []


def call_mcp_tool(name: str, arguments: Optional[dict] = None) -> Any:
    headers = _identity_headers()
    args = dict(arguments or {})
    tenant = headers.get("X-Tenant-ID")
    if tenant:
        args.setdefault("tenant_id", tenant)
    result = _rpc("tools/call", {"name": name, "arguments": args}, headers)
    content = (result or {}).get("content") or []
    if content and content[0].get("text"):
        try:
            return json.loads(content[0]["text"])
        except json.JSONDecodeError:
            return content[0]["text"]
    return result


def langchain_tools():
    try:
        from langchain_core.tools import StructuredTool
    except ImportError:
        return []
    tools = []
    for spec in list_mcp_tools():
        name = spec.get("name") or ""
        if not name:
            continue
        description = spec.get("description") or name

        def _make(tool_name: str):
            def _run(**kwargs):
                return call_mcp_tool(tool_name, kwargs)

            return _run

        tools.append(
            StructuredTool.from_function(
                func=_make(name),
                name=name.replace("-", "_"),
                description=description,
            )
        )
    return tools


def patch_langgraph() -> None:
    extra = langchain_tools()
    if not extra:
        logger.info("Mode B: no MCP tools to inject")
        return
    try:
        from langgraph.prebuilt import ToolNode
        from langgraph.prebuilt.chat_agent_executor import create_react_agent
    except ImportError:
        try:
            from langgraph.prebuilt import ToolNode, create_react_agent
        except ImportError:
            logger.info("Mode B: langgraph.prebuilt not available")
            return

    orig_toolnode = ToolNode.__init__

    def _toolnode_init(self, tools, *args, **kwargs):
        merged = list(tools or []) + extra
        orig_toolnode(self, merged, *args, **kwargs)

    ToolNode.__init__ = _toolnode_init  # type: ignore[method-assign]

    orig_react = create_react_agent

    def _react(model, tools=None, *args, **kwargs):
        merged = list(tools or []) + extra
        return orig_react(model, merged, *args, **kwargs)

    try:
        import langgraph.prebuilt as prebuilt
        prebuilt.create_react_agent = _react
        prebuilt.ToolNode = ToolNode
    except Exception:
        pass
    logger.info("Mode B: injected %s MCP tools", len(extra))
