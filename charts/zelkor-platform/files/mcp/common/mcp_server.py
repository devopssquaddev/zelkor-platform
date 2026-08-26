"""Minimal MCP/1.0 JSON-RPC over HTTP server."""
import json
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
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
            self._send_json(404, {"error": "not found"})

        def do_POST(self):
            if self.path not in ("/mcp", "/"):
                self._send_json(404, {"error": "not found"})
                return

            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            try:
                req = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
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
                elif method == "tools/list":
                    result = {"tools": tool_handler.list_tools()}
                elif method == "tools/call":
                    name = params.get("name")
                    arguments = params.get("arguments") or {}
                    if not tenant_id:
                        raise PermissionError("Missing tenant identity in Authorization or X-Tenant-ID header")
                    result = {"content": [{"type": "text", "text": json.dumps(tool_handler.call_tool(name, arguments, tenant_id))}]}
                elif method == "ping":
                    result = {}
                else:
                    self._send_json(200, {"jsonrpc": "2.0", "error": {"code": -32601, "message": f"Method not found: {method}"}, "id": req_id})
                    return

                self._send_json(200, {"jsonrpc": "2.0", "result": result, "id": req_id})
            except PermissionError as exc:
                self._send_json(200, {"jsonrpc": "2.0", "error": {"code": -32001, "message": str(exc)}, "id": req_id})
            except Exception as exc:
                logger.exception("MCP tool error")
                self._send_json(200, {"jsonrpc": "2.0", "error": {"code": -32603, "message": str(exc)}, "id": req_id})

    return MCPHandler


def run_mcp_server(tool_handler: MCPToolHandler, tenant_extractor, host: str = "0.0.0.0", port: int = 8080) -> None:
    handler = make_handler(tool_handler, tenant_extractor)
    server = HTTPServer((host, port), handler)
    logger.info("MCP server listening on %s:%s", host, port)
    server.serve_forever()
