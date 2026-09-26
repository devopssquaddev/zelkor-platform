"""
Unified MCP gateway — multiplexes native servers and workspace.tools.extraBackends.
Tool names are prefixed: postgres__query, qdrant__search_documents, sandbox__execute_python, egress__call_external_api
"""
import json
import logging
import os
import sys
import threading
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.mcp_server import MCPToolHandler, run_mcp_server
from common.tenant import extract_tenant
from gateway.backend_config import (
    BackendConfig,
    merge_backends,
    parse_extra_backends,
    rpc_call,
)

logger = logging.getLogger("zelkor-mcp-gateway")

POSTGRES_MCP_URL = os.getenv("POSTGRES_MCP_URL", "").strip()
QDRANT_MCP_URL = os.getenv("QDRANT_MCP_URL", "").strip()
SANDBOX_MCP_URL = os.getenv("SANDBOX_MCP_URL", "").strip()
EGRESS_MCP_URL = os.getenv("EGRESS_MCP_URL", "").strip()


def native_backends() -> Dict[str, str]:
    backends: Dict[str, str] = {}
    if POSTGRES_MCP_URL:
        backends["postgres"] = POSTGRES_MCP_URL
    if QDRANT_MCP_URL:
        backends["qdrant"] = QDRANT_MCP_URL
    if SANDBOX_MCP_URL:
        backends["sandbox"] = SANDBOX_MCP_URL
    if EGRESS_MCP_URL:
        backends["egress"] = EGRESS_MCP_URL
    return backends


def load_backends() -> Dict[str, BackendConfig]:
    extra = parse_extra_backends(os.getenv("MCP_EXTRA_BACKENDS", "[]"))
    return merge_backends(native_backends(), extra)


BACKENDS = load_backends()

_request_headers = threading.local()


def _get_headers() -> Dict[str, str]:
    return getattr(_request_headers, "value", {})


from gateway.backend_config import RESERVED_PREFIXES, validate_extra_name  # noqa: E402 — re-export for tests


def _rpc_call(cfg: BackendConfig, method: str, params: dict) -> Any:
    return rpc_call(cfg, method, params, _get_headers())


class GatewayMCPServer(MCPToolHandler):
    def list_tools(self) -> List[Dict[str, Any]]:
        tools: List[Dict[str, Any]] = []
        for prefix, cfg in BACKENDS.items():
            try:
                result = _rpc_call(cfg, "tools/list", {})
                n = 0
                for tool in result.get("tools") or []:
                    t = dict(tool)
                    t["name"] = f"{prefix}__{tool['name']}"
                    tools.append(t)
                    n += 1
                logger.debug("listed %s tools from backend %s", n, prefix)
            except Exception as exc:
                logger.warning("Failed to list tools from %s: %s", prefix, exc)
        logger.info(
            "MCP gateway backends=%s tools=%s",
            ",".join(sorted(BACKENDS)),
            len(tools),
            extra={"event": "tools_list"},
        )
        return tools

    def call_tool(self, name: str, arguments: dict, tenant_id: str) -> Any:
        if "__" not in name:
            raise ValueError(f"Tool must be prefixed: {name}")
        prefix, tool_name = name.split("__", 1)
        if prefix not in BACKENDS:
            raise ValueError(f"Unknown backend prefix: {prefix}")

        cfg = BACKENDS[prefix]
        args = dict(arguments)
        if cfg.inject_tenant_arg:
            args.setdefault("tenant_id", tenant_id)

        logger.debug(
            "forward tools/call %s to %s",
            tool_name,
            prefix,
            extra={"event": "tools_call", "tenant_id": tenant_id},
        )
        result = _rpc_call(cfg, "tools/call", {"name": tool_name, "arguments": args})
        text = (result.get("content") or [{}])[0].get("text", "{}")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"raw": text}


def _tenant_with_headers(headers: Dict[str, str]):
    _request_headers.value = headers
    return extract_tenant(headers)


if __name__ == "__main__":
    if not BACKENDS:
        logger.warning(
            "MCP gateway has no backends configured; tools/list will be empty",
            extra={"event": "startup"},
        )
    run_mcp_server(GatewayMCPServer(), _tenant_with_headers, port=int(os.getenv("PORT", "8080")))
