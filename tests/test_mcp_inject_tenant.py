"""Unit tests for Mode B tenant identity (no cluster, no MCP adapters)."""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "images" / "aegra"))

from mcp_inject import (  # noqa: E402
    _stamp_tenant_kwargs,
    _stamp_tenant_on_tool,
    tenant_from_run_config,
)


def test_tenant_from_auth_user_dict():
    cfg = {
        "configurable": {
            "langgraph_auth_user": {"identity": "Bank_Alpha", "tenant_id": "Bank_Alpha"}
        }
    }
    assert tenant_from_run_config(cfg) == "Bank_Alpha"


def test_tenant_from_auth_user_object():
    user = SimpleNamespace(identity="Bank_Alpha", tenant_id="Bank_Alpha")
    cfg = {"configurable": {"langgraph_auth_user": user}}
    assert tenant_from_run_config(cfg) == "Bank_Alpha"


def test_tenant_from_aegra_user_id_fallback():
    cfg = {"configurable": {"user_id": "Bank_Alpha"}}
    assert tenant_from_run_config(cfg) == "Bank_Alpha"


def test_tenant_from_run_config_ignores_empty():
    assert tenant_from_run_config({}) == ""
    assert tenant_from_run_config(None) == ""


def test_mode_b_does_not_wrap_create_deep_agent():
    text = Path(__file__).resolve().parents[1].joinpath("images/aegra/mcp_inject.py").read_text()
    assert "create_agent" in text
    assert "create_deep_agent" not in text


def test_stamp_tenant_kwargs_overwrites_model_guess(monkeypatch):
    monkeypatch.setattr(
        "mcp_inject.tenant_from_run_config", lambda config=None: "Bank_Alpha"
    )
    assert _stamp_tenant_kwargs({"tenant_id": "current_user", "sql": "SELECT 1"})[
        "tenant_id"
    ] == "Bank_Alpha"


class _FakeTool:
    def __init__(
        self,
        *,
        func=None,
        coroutine=None,
        name="postgres__query",
        response_format=None,
    ):
        self.func = func
        self.coroutine = coroutine
        self.name = name
        self.handle_tool_error = None
        self.response_format = response_format

    def model_copy(self, update=None):
        next_tool = _FakeTool(
            func=self.func,
            coroutine=self.coroutine,
            name=self.name,
            response_format=self.response_format,
        )
        next_tool.handle_tool_error = self.handle_tool_error
        for key, value in (update or {}).items():
            setattr(next_tool, key, value)
        return next_tool


def test_stamp_tenant_on_tool_returns_exception_as_content(monkeypatch):
    monkeypatch.setattr(
        "mcp_inject.tenant_from_run_config", lambda config=None: "Bank_Alpha"
    )

    def boom(**kwargs):
        assert kwargs["tenant_id"] == "Bank_Alpha"
        raise RuntimeError('relation "portfolio" does not exist')

    wrapped = _stamp_tenant_on_tool(_FakeTool(func=boom))
    text = wrapped.func(sql="SELECT 1", tenant_id="current")
    assert text.startswith("Error: RuntimeError:")
    assert "portfolio" in text
    assert wrapped.handle_tool_error is True


def test_stamp_tenant_on_tool_content_and_artifact_tuple(monkeypatch):
    monkeypatch.setattr(
        "mcp_inject.tenant_from_run_config", lambda config=None: "Bank_Alpha"
    )

    def boom(**kwargs):
        raise RuntimeError('column "valuation" does not exist')

    wrapped = _stamp_tenant_on_tool(
        _FakeTool(func=boom, response_format="content_and_artifact")
    )
    content, artifact = wrapped.func(sql="SELECT 1", tenant_id="current")
    assert content.startswith("Error: RuntimeError:")
    assert artifact is None
