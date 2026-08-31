"""Unit tests for Mode B MCP tool binder (no cluster)."""
import pytest

pytest.skip(
    "Postponed: rewrite after langchain-mcp-adapters became a hard import "
    "(no JSON-RPC binder / list_mcp_tools / call_mcp_tool).",
    allow_module_level=True,
)

import os
import sys
from pathlib import Path
from unittest.mock import patch

pytest.importorskip("langchain_core")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "images" / "aegra"))

from mcp_inject import (  # noqa: E402
    _wrap_agent_factory,
    call_mcp_tool,
    identity_headers,
    langchain_tools,
    list_mcp_tools,
    tenant_from_run_config,
)


def test_sitecustomize_imports_mcp_inject_from_app():
    text = (Path(__file__).resolve().parents[1] / "images/aegra/sitecustomize.py").read_text()
    assert 'sys.path.insert(0, "/app")' in text
    assert "os._exit(1)" in text


def test_list_mcp_tools_empty_without_url():
    with patch.dict("os.environ", {"MCP_URL": ""}, clear=False):
        assert list_mcp_tools() == []


def test_langchain_tools_from_fake_list():
    fake = [
        {
            "name": "postgres__query",
            "description": "SQL",
            "inputSchema": {"type": "object"},
        }
    ]
    with patch("mcp_inject.list_mcp_tools", return_value=fake):
        tools = langchain_tools()
    names = [t.name for t in tools]
    assert "postgres__query" in names
    assert "inputSchema" in tools[0].description


def test_wrap_agent_factory_merges_tools():
    captured = {}

    def factory(model, tools=None, **kwargs):
        captured["tools"] = tools
        captured["kwargs"] = kwargs
        return "graph"

    wrapped = _wrap_agent_factory(factory, ["mcp_tool"])
    assert wrapped("model", tools=["own"], system_prompt="hi") == "graph"
    assert captured["tools"] == ["own", "mcp_tool"]
    assert captured["kwargs"]["system_prompt"] == "hi"


def test_inject_ready_when_disabled(monkeypatch, tmp_path):
    monkeypatch.delenv("MCP_INJECT_ENABLED", raising=False)
    monkeypatch.setenv("MCP_INJECT_STATUS_PATH", str(tmp_path / "status"))
    from importlib import reload
    import mcp_inject

    reload(mcp_inject)
    assert mcp_inject.inject_ready() is True


def test_inject_ready_requires_ok_status(monkeypatch, tmp_path):
    status = tmp_path / "status"
    monkeypatch.setenv("MCP_INJECT_ENABLED", "true")
    monkeypatch.setenv("MCP_INJECT_STATUS_PATH", str(status))
    from importlib import reload
    import mcp_inject

    reload(mcp_inject)
    assert mcp_inject.inject_ready() is False
    mcp_inject.write_inject_status("ok")
    assert mcp_inject.inject_ready() is True


def test_tenant_from_run_config_uses_auth_user():
    cfg = {
        "configurable": {
            "langgraph_auth_user": {"identity": "Bank_Alpha", "tenant_id": "Bank_Alpha"}
        }
    }
    assert tenant_from_run_config(cfg) == "Bank_Alpha"


def test_tenant_from_run_config_ignores_empty():
    assert tenant_from_run_config({}) == ""
    assert tenant_from_run_config(None) == ""


def test_call_mcp_tool_uses_config_tenant_not_env():
    captured = {}

    def fake_rpc(method, params, headers=None):
        captured["method"] = method
        captured["headers"] = headers
        captured["params"] = params
        return {"content": [{"type": "text", "text": "{}"}]}

    env = {
        "ZELKOR_TENANT_ID": "Bank_Beta",
        "AUTH_DEV_TOKEN_PREFIX": "dev:",
        "MCP_URL": "http://mcp.example:8080",
    }
    cfg = {"configurable": {"langgraph_auth_user": {"identity": "Bank_Alpha"}}}
    with patch.dict(os.environ, env, clear=False):
        with patch("mcp_inject._rpc", side_effect=fake_rpc):
            call_mcp_tool("postgres__query", {"sql": "SELECT 1"}, config=cfg)

    assert captured["headers"]["X-Tenant-ID"] == "Bank_Alpha"
    assert captured["params"]["arguments"]["tenant_id"] == "Bank_Alpha"
    assert captured["headers"]["Authorization"] == "Bearer dev:Bank_Alpha"
    assert "Bank_Beta" not in captured["headers"]["Authorization"]


def test_identity_headers_empty_without_run_tenant():
    with patch.dict(os.environ, {"ZELKOR_TENANT_ID": "Bank_Beta", "AUTH_DEV_TOKEN_PREFIX": "dev:"}, clear=False):
        headers = identity_headers({})
    assert "X-Tenant-ID" not in headers
    assert "Authorization" not in headers
