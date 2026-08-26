"""
Unified MCP gateway — multiplexes postgres, qdrant, and sandbox MCP backends.
Tool names are prefixed: postgres__query, qdrant__search_documents, sandbox__execute_python
"""
import json
import logging
import os
import sys
import threading
import urllib.request
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.mcp_server import MCPToolHandler, run_mcp_server
from common.tenant import extract_tenant

logger = logging.getLogger("mcp-gateway")

POSTGRES_MCP_URL = os.getenv("POSTGRES_MCP_URL", "http://zelkor-platform-mcp-postgres:8080")
QDRANT_MCP_URL = os.getenv("QDRANT_MCP_URL", "http://zelkor-platform-mcp-qdrant:8080")
SANDBOX_MCP_URL = os.getenv("SANDBOX_MCP_URL", "http://zelkor-platform-mcp-sandbox:8080")

BACKENDS = {
    "postgres": POSTGRES_MCP_URL,
    "qdrant": QDRANT_MCP_URL,
    "sandbox": SANDBOX_MCP_URL,
}

_request_headers = threading.local()


def _get_headers() -> Dict[str, str]:
    return getattr(_request_headers, "value", {})


def _rpc_call(base_url: str, method: str, params: dict) -> Any:
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode("utf-8")
    hdrs = {"Content-Type": "application/json"}
    hdrs.update({k: v for k, v in _get_headers().items() if k.lower() in ("authorization", "x-tenant-id")})
    req = urllib.request.Request(f"{base_url.rstrip('/')}/mcp", data=payload, headers=hdrs, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        if "error" in data:
            raise RuntimeError(data["error"].get("message", str(data["error"])))
        return data.get("result")


class GatewayMCPServer(MCPToolHandler):
    def list_tools(self) -> List[Dict[str, Any]]:
        tools: List[Dict[str, Any]] = []
        for prefix, url in BACKENDS.items():
            try:
                result = _rpc_call(url, "tools/list", {})
                for tool in result.get("tools") or []:
                    t = dict(tool)
                    t["name"] = f"{prefix}__{tool['name']}"
                    tools.append(t)
            except Exception as exc:
                logger.warning("Failed to list tools from %s: %s", prefix, exc)
        return tools

    def call_tool(self, name: str, arguments: dict, tenant_id: str) -> Any:
        if "__" not in name:
            raise ValueError(f"Tool must be prefixed: {name}")
        prefix, tool_name = name.split("__", 1)
        if prefix not in BACKENDS:
            raise ValueError(f"Unknown backend prefix: {prefix}")

        args = dict(arguments)
        args.setdefault("tenant_id", tenant_id)

        result = _rpc_call(BACKENDS[prefix], "tools/call", {"name": tool_name, "arguments": args})
        text = (result.get("content") or [{}])[0].get("text", "{}")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"raw": text}


def _tenant_with_headers(headers: Dict[str, str]):
    _request_headers.value = headers
    return extract_tenant(headers)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_mcp_server(GatewayMCPServer(), _tenant_with_headers, port=int(os.getenv("PORT", "8080")))
