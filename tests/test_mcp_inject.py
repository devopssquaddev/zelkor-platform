"""Unit tests for Mode B MCP inject helpers (no cluster)."""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

pytest.importorskip("langchain_core")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "images" / "aegra"))

from mcp_inject import (  # noqa: E402
    _wrap_agent_factory,
    inject_ready,
    patch_langgraph,
    tenant_from_run_config,
    write_inject_status,
)


def test_sitecustomize_imports_mcp_inject_from_app():
    text = (Path(__file__).resolve().parents[1] / "images/aegra/sitecustomize.py").read_text()
    assert 'sys.path.insert(0, "/app")' in text
    assert "patch_langgraph" in text


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
