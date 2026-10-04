"""Unit tests for Mode B MCP inject helpers (no cluster)."""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

pytest.importorskip("langchain_core")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "images" / "aegra"))

from mcp_inject import (  # noqa: E402
    _mcp_url,
    _wrap_agent_factory,
    call_tool,
    inject_ready,
    mcp_run_session,
    patch_langgraph,
    tenant_from_run_config,
    write_inject_status,
)


def test_sitecustomize_imports_mcp_inject_from_app():
    text = (Path(__file__).resolve().parents[1] / "images/aegra/sitecustomize.py").read_text()
    assert 'sys.path.insert(0, "/app")' in text
    assert "install_agent_step_callback" in text
    assert "patch_langgraph" in text
    assert text.find("patch_pregel_mcp_session") < text.find("patch_pregel()")


def test_module_level_create_agent_returns_factory():
    def orig(*_args, **_kwargs):
        return "COMPILED"

    wrapped = _wrap_agent_factory(orig)
    with patch("mcp_inject._is_module_level_create_agent_call", return_value=True):
        factory = wrapped("model", tools=["own"])
    assert factory.__name__ == "zelkor_mode_b_graph"
    assert callable(factory)


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


def test_patch_langgraph_does_not_open_mcp(monkeypatch):
    import mcp_inject

    with patch.object(mcp_inject, "_mcp_client_session") as mock_sess:
        mock_sess.side_effect = AssertionError("import-time MCP")
        with patch.object(mcp_inject, "_patch_factory", return_value=True):
            patch_langgraph()
        mock_sess.assert_not_called()


def test_mcp_url_does_not_double_suffix(monkeypatch):
    monkeypatch.setenv("MCP_URL", "http://zelkor-platform-mcp/mcp")
    assert _mcp_url() == "http://zelkor-platform-mcp/mcp"
    monkeypatch.setenv("MCP_URL", "http://zelkor-platform-mcp")
    assert _mcp_url() == "http://zelkor-platform-mcp/mcp"


def test_call_tool_fails_closed_without_url(monkeypatch):
    import asyncio

    monkeypatch.delenv("MCP_URL", raising=False)
    with patch("mcp_inject.inbound_authorization", return_value="Bearer x"):
        out = asyncio.run(call_tool("tavily__tavily_search", {"query": "x"}))
    assert out.startswith("Error:")
    assert "MCP_URL" in out


def test_call_tool_session_error_is_tool_text(monkeypatch):
    import asyncio
    from contextlib import asynccontextmanager

    import mcp_inject

    @asynccontextmanager
    async def boom(_bearer):
        raise RuntimeError("Session terminated")
        yield None

    monkeypatch.setenv("MCP_URL", "http://zelkor-platform-mcp/mcp")
    with patch.object(mcp_inject, "inbound_authorization", return_value="Bearer jwt"):
        with patch.object(mcp_inject, "_mcp_client_session", boom):
            out = asyncio.run(mcp_inject.call_tool("tavily__tavily_search", {"query": "x"}))
    assert out.startswith("Error:")
    assert "Session terminated" in out


def test_call_tool_reuses_run_session(monkeypatch):
    import asyncio
    from contextlib import asynccontextmanager
    from types import SimpleNamespace

    import mcp_inject

    inits = {"n": 0}

    class Sess:
        def __init__(self):
            inits["n"] += 1

        async def call_tool(self, name, arguments):
            return SimpleNamespace(isError=False, content=[SimpleNamespace(text=name)])

    @asynccontextmanager
    async def fake_session(_bearer):
        yield Sess()

    async def two():
        async with mcp_run_session():
            a = await mcp_inject.call_tool("tavily__tavily_search", {"query": "a"})
            b = await mcp_inject.call_tool("tavily__tavily_research", {"input": "b"})
            return a, b

    monkeypatch.setenv("MCP_URL", "http://zelkor-platform-mcp/mcp")
    with patch.object(mcp_inject, "inbound_authorization", return_value="Bearer jwt"):
        with patch.object(mcp_inject, "_mcp_client_session", fake_session):
            a, b = asyncio.run(two())
    assert inits["n"] == 1
    assert a == "tavily__tavily_search"
    assert b == "tavily__tavily_research"


def test_call_tool_opens_session_after_identity(monkeypatch):
    import asyncio
    from contextlib import asynccontextmanager
    from types import SimpleNamespace

    import mcp_inject

    inits = {"n": 0}
    bearer = {"v": ""}

    class Sess:
        def __init__(self):
            inits["n"] += 1

        async def call_tool(self, name, arguments):
            return SimpleNamespace(isError=False, content=[SimpleNamespace(text=name)])

    @asynccontextmanager
    async def fake_session(_bearer):
        assert _bearer == "Bearer jwt"
        yield Sess()

    async def two():
        bearer["v"] = "Bearer jwt"
        async with mcp_run_session():
            a = await mcp_inject.call_tool("tavily__tavily_search", {"query": "a"})
            b = await mcp_inject.call_tool("tavily__tavily_research", {"input": "b"})
            return a, b

    monkeypatch.setenv("MCP_URL", "http://zelkor-platform-mcp/mcp")
    with patch.object(mcp_inject, "inbound_authorization", lambda: bearer["v"]):
        with patch.object(mcp_inject, "_mcp_client_session", fake_session):
            a, b = asyncio.run(two())
    assert inits["n"] == 1
    assert a == "tavily__tavily_search"
    assert b == "tavily__tavily_research"


def test_call_tool_uses_session(monkeypatch):
    import asyncio
    from contextlib import asynccontextmanager
    from types import SimpleNamespace

    import mcp_inject

    class Sess:
        async def call_tool(self, name, arguments):
            assert name == "tavily__tavily_search"
            return SimpleNamespace(isError=False, content=[SimpleNamespace(text="ok")])

    @asynccontextmanager
    async def fake_session(_bearer):
        yield Sess()

    monkeypatch.setenv("MCP_URL", "http://zelkor-platform-mcp/mcp")
    with patch.object(mcp_inject, "inbound_authorization", return_value="Bearer jwt"):
        with patch.object(mcp_inject, "_mcp_client_session", fake_session):
            assert asyncio.run(mcp_inject.call_tool("tavily__tavily_search", {"query": "x"})) == "ok"


def test_call_tool_timeout_is_error_text(monkeypatch):
    import asyncio
    from contextlib import asynccontextmanager

    import mcp_inject

    class Sess:
        async def call_tool(self, name, arguments):
            await asyncio.sleep(2)
            raise AssertionError("should have timed out")

    @asynccontextmanager
    async def fake_session(_bearer):
        yield Sess()

    monkeypatch.setenv("MCP_URL", "http://zelkor-platform-mcp/mcp")
    monkeypatch.setenv("ZELKOR_MCP_TOOL_TIMEOUT_SEC", "0.05")
    with patch.object(mcp_inject, "inbound_authorization", return_value="Bearer jwt"):
        with patch.object(mcp_inject, "_mcp_client_session", fake_session):
            out = asyncio.run(mcp_inject.call_tool("tavily__tavily_research", {"input": "secret"}))
    assert out.startswith("Error:")
    assert "TimeoutError" in out
    assert "secret" not in out


def test_mcp_rpc_debug_has_id_not_args(monkeypatch, caplog):
    import asyncio
    import logging
    from contextlib import asynccontextmanager
    from types import SimpleNamespace

    import mcp_inject

    class Sess:
        async def call_tool(self, name, arguments):
            return SimpleNamespace(isError=False, content=[SimpleNamespace(text="ok")])

    @asynccontextmanager
    async def fake_session(_bearer):
        yield Sess()

    monkeypatch.setenv("MCP_URL", "http://zelkor-platform-mcp/mcp")
    with caplog.at_level(logging.DEBUG, logger="zelkor-mcp-inject"):
        with patch.object(mcp_inject, "inbound_authorization", return_value="Bearer jwt"):
            with patch.object(mcp_inject, "_mcp_client_session", fake_session):
                asyncio.run(mcp_inject.call_tool("tavily__tavily_search", {"query": "secret-arg"}))
    joined = caplog.text
    assert "mcp rpc" in joined
    assert "secret-arg" not in joined
    assert "Bearer jwt" not in joined
