"""Unit tests for MCP HTTP server hardening (no cluster)."""
import json
import sys
import threading
from http.server import HTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp"))

from common.mcp_server import MCPToolHandler, make_handler  # noqa: E402


class _StubHandler(MCPToolHandler):
    def list_tools(self):
        return []

    def call_tool(self, name, arguments, tenant_id):
        return {}


def test_mcp_rejects_oversized_body(monkeypatch):
    monkeypatch.setattr("common.mcp_server.MAX_BODY_BYTES", 64)
    handler_cls = make_handler(_StubHandler(), lambda _h: "tenant-a")
    server = HTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        url = f"http://127.0.0.1:{port}/mcp"
        payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {}}).encode()
        oversized = payload + (b"x" * 128)
        req = Request(
            url,
            data=oversized,
            headers={"Content-Type": "application/json", "Content-Length": str(len(oversized))},
            method="POST",
        )
        with pytest.raises(HTTPError) as exc_info:
            urlopen(req, timeout=3)
        assert exc_info.value.code == 413
        thread.join(timeout=5)
    finally:
        server.server_close()
