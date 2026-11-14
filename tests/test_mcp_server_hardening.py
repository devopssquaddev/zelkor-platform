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


class _KindHandler(MCPToolHandler):
    seen_trace: dict = {}

    def list_tools(self):
        return [{"name": n, "inputSchema": {"type": "object"}} for n in ("bad_args", "boom", "trace")]

    def call_tool(self, name, arguments, tenant_id, limiter=None):
        from common.mcp_server import TRACE_CONTEXT

        if name == "bad_args":
            raise ValueError("messages is required")
        if name == "boom":
            raise RuntimeError("backend exploded")
        _KindHandler.seen_trace = dict(TRACE_CONTEXT.get())
        return {"ok": True}


def _rpc_call(client, name, *, meta=None, headers=None):
    params = {"name": name, "arguments": {}}
    if meta:
        params["_meta"] = meta
    resp = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": params},
                       headers={"accept": "application/json, text/event-stream", **(headers or {})})
    assert resp.status_code == 200, resp.text
    return resp.json()["result"]


def test_failed_tool_calls_carry_a_failure_class():
    """Callers stamp error.type from _meta["zelkor.error"]; the text stays the exception message."""
    with TestClient(build_starlette_app(_KindHandler(), lambda _h: "tenant-a")) as client:
        bad = _rpc_call(client, "bad_args")
        boom = _rpc_call(client, "boom")
    assert bad["isError"] and bad["_meta"]["zelkor.error"] == "invalid_arguments"
    assert "messages is required" in bad["content"][0]["text"]
    assert boom["isError"] and boom["_meta"]["zelkor.error"] == "error"


def test_tool_sees_the_gateway_span_from_meta_before_forwarded_headers():
    gw = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
    caller = "00-0af7651916cd43dd8448eb211c80319c-00f067aa0ba902b7-01"
    with TestClient(build_starlette_app(_KindHandler(), lambda _h: "tenant-a")) as client:
        _rpc_call(client, "trace", meta={"traceparent": gw}, headers={"traceparent": caller})
        assert _KindHandler.seen_trace == {"traceparent": gw}
        _rpc_call(client, "trace", headers={"traceparent": caller})
        assert _KindHandler.seen_trace == {"traceparent": caller}
