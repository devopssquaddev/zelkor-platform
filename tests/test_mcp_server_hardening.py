"""Unit tests for MCP HTTP server hardening (no cluster)."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp"))

pytest.importorskip("starlette")
from starlette.testclient import TestClient  # noqa: E402

from common.mcp_server import (  # noqa: E402
    MCPToolHandler,
    _reject_stray_tenant_id,
    build_starlette_app,
)


class _StubHandler(MCPToolHandler):
    def list_tools(self):
        return []

    def call_tool(self, name, arguments, tenant_id):
        return {}


def test_mcp_rejects_oversized_body(monkeypatch):
    monkeypatch.setattr("common.mcp_server.MAX_BODY_BYTES", 64)
    app = build_starlette_app(_StubHandler(), lambda _h: "tenant-a")
    with TestClient(app) as client:
        response = client.post(
            "/mcp",
            content=b"x" * 200,
            headers={"content-type": "application/json"},
        )
    assert response.status_code == 413


def test_mcp_health_endpoint():
    app = build_starlette_app(_StubHandler(), lambda _h: "tenant-a")
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_mcp_exact_path_is_not_redirect():
    """Starlette Route(\"/mcp\") must not 307/308 to /mcp/."""
    app = build_starlette_app(_StubHandler(), lambda _h: "tenant-a")
    with TestClient(app, follow_redirects=False) as client:
        response = client.post(
            "/mcp",
            content=b"{}",
            headers={"content-type": "application/json", "accept": "application/json"},
        )
    assert response.status_code not in (307, 308)
    assert response.status_code != 404


def test_reject_stray_tenant_id():
    with pytest.raises(PermissionError, match="tenant_id argument is not allowed"):
        _reject_stray_tenant_id({"sql": "SELECT 1", "tenant_id": "spoof"})
    _reject_stray_tenant_id({"sql": "SELECT 1"})


def test_native_tool_schemas_omit_tenant_id():
    from wrappers.aigateway_server import AIGatewayMCPServer
    from wrappers.postgres_server import PostgresMCPServer
    from wrappers.qdrant_server import QdrantMCPServer
    from sandbox.server import SandboxMCPServer

    servers = [
        PostgresMCPServer(),
        QdrantMCPServer(),
        AIGatewayMCPServer(allowed_models=[]),
        SandboxMCPServer(),
    ]
    for server in servers:
        for tool in server.list_tools():
            schema = tool["inputSchema"]
            assert "tenant_id" not in schema.get("properties", {}), tool["name"]
            assert schema.get("additionalProperties") is False, tool["name"]


def test_sandbox_timeout_clamped(monkeypatch):
    from sandbox import server as sandbox_mod

    monkeypatch.setattr(sandbox_mod, "MAX_TIMEOUT", 90)
    captured = {}

    def fake_execute(code, tenant_id, timeout=5):
        captured["timeout"] = timeout
        return {"ok": True}

    monkeypatch.setattr(sandbox_mod, "execute_on_worker", fake_execute)
    sandbox_mod.SandboxMCPServer().call_tool(
        "execute_python",
        {"code": "print(1)", "timeout": 999},
        "tenant-a",
    )
    assert captured["timeout"] == 90
