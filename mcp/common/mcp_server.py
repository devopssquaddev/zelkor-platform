"""Minimal MCP/1.0 JSON-RPC over HTTP server."""
import json
import logging
import os
import signal
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from socketserver import ThreadingMixIn
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("zelkor-mcp")

MAX_BODY_BYTES = int(os.getenv("MCP_MAX_BODY_BYTES", "1048576"))
MAX_CONCURRENT_REQUESTS = int(os.getenv("MCP_MAX_CONCURRENT_REQUESTS", "32"))
_request_semaphore = threading.Semaphore(MAX_CONCURRENT_REQUESTS)

try:
    from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest
except ImportError:  # image extra; local unit tests without the dep
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"
    Counter = None  # type: ignore[assignment]
    generate_latest = None  # type: ignore[assignment]

_MCP_REQUESTS = (
    Counter(
        "zelkor_mcp_http_requests_total",
        "MCP HTTP requests by method, handler, and status",
        ["method", "handler", "code"],
    )
    if Counter is not None
    else None
)
_MCP_ERRORS = (
    Counter(
        "zelkor_mcp_http_errors_total",
        "MCP HTTP 5xx responses",
        ["method", "handler"],
    )
    if Counter is not None
    else None
)


def _handler_label(path: str) -> str:
    route = (path or "/").split("?", 1)[0]
    if route in ("/health", "/healthz"):
        return "health"
    if route == "/metrics":
        return "metrics"
    if route in ("/mcp", "/"):
        return "mcp"
    return "other"


def _observe(method: str, path: str, code: int) -> None:
    if _MCP_REQUESTS is None:
        return
    handler = _handler_label(path)
    if handler in ("health", "metrics"):
        return
    _MCP_REQUESTS.labels(method=method, handler=handler, code=str(code)).inc()
    if int(code) >= 500 and _MCP_ERRORS is not None:
        _MCP_ERRORS.labels(method=method, handler=handler).inc()


class MCPToolHandler:
    def list_tools(self) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def call_tool(self, name: str, arguments: Dict[str, Any], tenant_id: Optional[str]) -> Any:
        raise NotImplementedError


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


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
            _observe(self.command, self.path, code)

        def do_GET(self):
            route = (self.path or "/").split("?", 1)[0]
            if route in ("/health", "/healthz"):
                self._send_json(200, {"status": "ok", "protocol": "mcp/1.0"})
                return
            if route == "/metrics":
                if generate_latest is None:
                    self._send_json(501, {"error": "metrics unavailable"})
                    return
                body = generate_latest()
                self.send_response(200)
                self.send_header("Content-Type", CONTENT_TYPE_LATEST)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            logger.debug("MCP GET not found: %s", self.path)
            self._send_json(404, {"error": "not found"})

        def do_POST(self):
            if self.path not in ("/mcp", "/"):
                logger.debug("MCP POST not found: %s", self.path)
                self._send_json(404, {"error": "not found"})
                return

            if not _request_semaphore.acquire(blocking=False):
                self._send_json(503, {"jsonrpc": "2.0", "error": {"code": -32003, "message": "Server busy"}, "id": None})
                return

            try:
                try:
                    length = int(self.headers.get("Content-Length", 0))
                except ValueError:
                    self._send_json(400, {"jsonrpc": "2.0", "error": {"code": -32700, "message": "Invalid Content-Length"}, "id": None})
                    return
                if length > MAX_BODY_BYTES:
                    self._send_json(413, {"jsonrpc": "2.0", "error": {"code": -32700, "message": "Request body too large"}, "id": None})
                    return

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
            finally:
                _request_semaphore.release()

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
    server = ThreadingHTTPServer((host, port), handler)
    logger.info(
        "MCP server listening on %s:%s max_body=%s max_concurrent=%s",
        host,
        port,
        MAX_BODY_BYTES,
        MAX_CONCURRENT_REQUESTS,
    )

    def _shutdown(signum, _frame):
        logger.info("MCP server shutdown signal=%s", signum, extra={"event": "shutdown"})
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)
    server.serve_forever()
    server.server_close()
