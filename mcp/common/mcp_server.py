"""Minimal MCP/1.0 JSON-RPC over HTTP server."""
import json
import logging
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("zelkor-mcp")


class MCPToolHandler:
    def list_tools(self) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def call_tool(self, name: str, arguments: Dict[str, Any], tenant_id: Optional[str]) -> Any:
        raise NotImplementedError


def make_handler(tool_handler: MCPToolHandler, tenant_extractor: Callable[[Dict[str, str]], Optional[str]]):
    class MCPHandler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            logger.debug(fmt, *args)

        def _headers_dict(self) -> Dict[str, str]:
            return {k: v for k, v in self.headers.items()}

        def _send_json(self, code: int, payload: Dict[str, Any]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path in ("/health", "/healthz"):
                self._send_json(200, {"status": "ok", "protocol": "mcp/1.0"})
                return
            logger.debug("MCP GET not found: %s", self.path)
            self._send_json(404, {"error": "not found"})

        def do_POST(self):
            if self.path not in ("/mcp", "/"):
                logger.debug("MCP POST not found: %s", self.path)
                self._send_json(404, {"error": "not found"})
                return

            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            try:
                req = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                logger.debug("MCP parse error")
                self._send_json(400, {"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}, "id": None})
                return

            req_id = req.get("id")
            method = req.get("method")
            params = req.get("params") or {}
            tenant_id = tenant_extractor(self._headers_dict())

            try:
                if method == "initialize":
                    result = {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "zelkor-mcp", "version": "0.1.0"},
                    }
                    logger.debug("MCP initialize")
                elif method == "tools/list":
                    tools = tool_handler.list_tools()
                    result = {"tools": tools}
                    logger.info(
                        "tools/list count=%s",
                        len(tools),
                        extra={"event": "tools_list", "tenant_id": tenant_id or ""},
                    )
                elif method == "tools/call":
                    name = params.get("name")
                    arguments = params.get("arguments") or {}
                    if not tenant_id:
                        raise PermissionError("Missing tenant identity in Authorization or X-Tenant-ID header")
                    result = {"content": [{"type": "text", "text": json.dumps(tool_handler.call_tool(name, arguments, tenant_id))}]}
                    logger.info(
                        "tools/call %s",
                        name,
                        extra={"event": "tools_call", "tenant_id": tenant_id},
                    )
                elif method == "ping":
                    result = {}
                    logger.debug("MCP ping")
                else:
                    logger.debug("MCP method not found: %s", method)
                    self._send_json(200, {"jsonrpc": "2.0", "error": {"code": -32601, "message": f"Method not found: {method}"}, "id": req_id})
                    return

                self._send_json(200, {"jsonrpc": "2.0", "result": result, "id": req_id})
            except PermissionError as exc:
                logger.warning(
                    "MCP permission denied: %s",
                    exc,
                    extra={"event": "tools_call", "tenant_id": tenant_id or ""},
                )
                self._send_json(200, {"jsonrpc": "2.0", "error": {"code": -32001, "message": str(exc)}, "id": req_id})
            except Exception as exc:
                logger.exception("MCP tool error")
                self._send_json(200, {"jsonrpc": "2.0", "error": {"code": -32603, "message": str(exc)}, "id": req_id})

    return MCPHandler


def _configure_logging() -> None:
    try:
        from zelkor_logging import configure_logging
    except ImportError:
        extra = Path(__file__).resolve().parents[2] / "images" / "common"
        if extra.is_dir() and str(extra) not in sys.path:
            sys.path.insert(0, str(extra))
        from zelkor_logging import configure_logging
    configure_logging(os.getenv("ZELKOR_LOG_COMPONENT", "zelkor-mcp"))


def run_mcp_server(tool_handler: MCPToolHandler, tenant_extractor, host: str = "0.0.0.0", port: int = 8080) -> None:
    _configure_logging()
    handler = make_handler(tool_handler, tenant_extractor)
    server = HTTPServer((host, port), handler)
    logger.info("MCP server listening on %s:%s", host, port)
    server.serve_forever()
