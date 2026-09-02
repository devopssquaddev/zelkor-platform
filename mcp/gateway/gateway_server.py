"""
Unified MCP gateway — multiplexes native servers and mcp.extraBackends.
Tool names are prefixed: postgres__query, qdrant__search_documents, sandbox__execute_python, egress__call_external_api
"""
import json
import logging
import os
import re
import sys
import threading
import urllib.request
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.mcp_server import MCPToolHandler, run_mcp_server
from common.tenant import extract_tenant

logger = logging.getLogger("zelkor-mcp-gateway")

POSTGRES_MCP_URL = os.getenv("POSTGRES_MCP_URL", "http://zelkor-platform-mcp-postgres:8080")
QDRANT_MCP_URL = os.getenv("QDRANT_MCP_URL", "http://zelkor-platform-mcp-qdrant:8080")
SANDBOX_MCP_URL = os.getenv("SANDBOX_MCP_URL", "http://zelkor-platform-mcp-sandbox:8080")
EGRESS_MCP_URL = os.getenv("EGRESS_MCP_URL", "").strip()

RESERVED_PREFIXES = frozenset({"postgres", "qdrant", "sandbox", "egress", "nemo", "aegra"})
_DNS_LABEL = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")


def native_backends() -> Dict[str, str]:
    backends = {
        "postgres": POSTGRES_MCP_URL,
        "qdrant": QDRANT_MCP_URL,
        "sandbox": SANDBOX_MCP_URL,
    }
    if EGRESS_MCP_URL:
        backends["egress"] = EGRESS_MCP_URL
    return backends


def parse_extra_backends(raw: str) -> List[Dict[str, str]]:
    text = (raw or "").strip()
    if not text:
        return []
    data = json.loads(text)
    if data is None:
        return []
    if not isinstance(data, list):
        raise ValueError("MCP_EXTRA_BACKENDS must be a JSON list of {name, url}")
    return data


def validate_extra_name(name: str) -> str:
    if not name or not isinstance(name, str):
        raise ValueError("extra backend name is required")
    if "__" in name:
        raise ValueError("extra backend name must not contain __")
    if name in RESERVED_PREFIXES:
        raise ValueError(f"extra backend name collides with reserved prefix: {name}")
    if not _DNS_LABEL.match(name):
        raise ValueError(f"extra backend name must be a DNS label: {name}")
    return name


def merge_backends(native: Dict[str, str], extra: List[Dict[str, str]]) -> Dict[str, str]:
    merged = dict(native)
    for item in extra:
        if not isinstance(item, dict):
            raise ValueError("extra backend entries must be objects with name and url")
        name = validate_extra_name((item.get("name") or "").strip())
        url = (item.get("url") or "").strip()
        if not url:
            raise ValueError(f"extra backend {name} is missing url")
        if name in merged:
            raise ValueError(f"extra backend name already in use: {name}")
        merged[name] = url
    return merged


def load_backends() -> Dict[str, str]:
    extra = parse_extra_backends(os.getenv("MCP_EXTRA_BACKENDS", "[]"))
    return merge_backends(native_backends(), extra)


BACKENDS = load_backends()

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

        args = dict(arguments)
        args.setdefault("tenant_id", tenant_id)

        logger.debug(
            "forward tools/call %s to %s",
            tool_name,
            prefix,
            extra={"event": "tools_call", "tenant_id": tenant_id},
        )
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
    run_mcp_server(GatewayMCPServer(), _tenant_with_headers, port=int(os.getenv("PORT", "8080")))
