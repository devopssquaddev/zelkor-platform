"""Generic extra MCP: tenant from claim headers; Authorization is not required."""
from __future__ import annotations

import logging
import os
import sys
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.mcp_server import MCPToolHandler, run_mcp_server

logger = logging.getLogger("zelkor-mcp-echo")

_LAST_HEADERS: Dict[str, str] = {}


def extract_extra_tenant(headers: Dict[str, str]) -> Optional[str]:
    _LAST_HEADERS.clear()
    _LAST_HEADERS.update({str(k).lower(): str(v) for k, v in headers.items()})
    for key in ("x-tenant-id",):
        raw = _LAST_HEADERS.get(key)
        if raw and raw.strip():
            return raw.strip()
    return None


class EchoMCPServer(MCPToolHandler):
    def list_tools(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "ping",
                "description": "Echo tenant claim headers and whether Authorization arrived.",
                "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
            }
        ]

    def call_tool(self, name: str, arguments: Dict[str, Any], tenant_id: Optional[str]) -> Any:
        if name != "ping":
            raise ValueError(f"unknown tool: {name}")
        auth = _LAST_HEADERS.get("authorization") or ""
        token = auth[7:].strip() if auth.lower().startswith("bearer ") else auth
        looks_jwt = token.startswith("eyJ") and token.count(".") >= 2
        return {
            "ok": True,
            "tenant_id": tenant_id,
            "has_authorization": bool(auth),
            "authorization_is_jwt": looks_jwt,
        }


if __name__ == "__main__":
    run_mcp_server(EchoMCPServer(), extract_extra_tenant, port=int(os.getenv("PORT", "8080")))
