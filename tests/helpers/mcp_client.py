"""Thin JSON-RPC client for Zelkor unified MCP gateway (platform tests)."""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

import httpx

GATEWAY_BASE_URL = os.environ.get("GATEWAY_BASE_URL", "http://127.0.0.1:8088")
MCP_HOST_HEADER = os.environ.get("MCP_HOST_HEADER", "mcp.localhost")


class MCPGatewayClient:
    def __init__(
        self,
        tenant_id: str,
        *,
        base_url: str = GATEWAY_BASE_URL,
        host_header: str = MCP_HOST_HEADER,
    ) -> None:
        self.tenant_id = tenant_id
        self.mcp_url = f"{base_url.rstrip('/')}/mcp"
        self.headers = {
            "Content-Type": "application/json",
            "Host": host_header,
            "Authorization": f"Bearer dev:{tenant_id}",
            "X-Tenant-ID": tenant_id,
        }

    def _post(self, payload: dict) -> dict:
        try:
            resp = httpx.post(self.mcp_url, headers=self.headers, json=payload, timeout=30.0)
            resp.raise_for_status()
            return resp.json()
        except httpx.ConnectError as exc:
            raise ConnectionError(f"MCP gateway not reachable at {self.mcp_url}") from exc

    def list_tools(self) -> List[Dict[str, Any]]:
        data = self._post({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
        if "error" in data:
            raise RuntimeError(data["error"].get("message", str(data["error"])))
        return (data.get("result") or {}).get("tools") or []

    def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Any:
        args = dict(arguments or {})
        args.setdefault("tenant_id", self.tenant_id)
        data = self._post({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": args},
        })
        if "error" in data:
            raise RuntimeError(data["error"].get("message", str(data["error"])))
        content = (data.get("result") or {}).get("content") or []
        if content and content[0].get("text"):
            return json.loads(content[0]["text"])
        return data.get("result")
