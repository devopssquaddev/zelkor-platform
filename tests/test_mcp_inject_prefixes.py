"""Unit tests for Mode B MCP tool prefix / name filtering."""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "images" / "aegra"))

from mcp_inject import (  # noqa: E402
    _parse_prefixes,
    _prefixes_from_module,
    _select_specs,
    filter_tools_by_prefix,
)


def _tool(name: str):
    return SimpleNamespace(name=name)


def test_parse_prefixes():
    assert _parse_prefixes("postgres, qdrant") == ("postgres", "qdrant")
    assert _parse_prefixes("") == ()


def test_prefixes_from_module_tuple():
    mod = SimpleNamespace(MCP_INJECT_PREFIXES=("postgres",))
    assert _prefixes_from_module(mod) == ("postgres",)


def test_prefixes_from_module_string():
    mod = SimpleNamespace(MCP_INJECT_PREFIXES="postgres,qdrant")
    assert _prefixes_from_module(mod) == ("postgres", "qdrant")


def test_filter_tools_by_prefix():
    tools = [
        _tool("postgres__query"),
        _tool("qdrant__search_documents"),
        _tool("sandbox__execute_python"),
    ]
    filtered = filter_tools_by_prefix(tools, ("postgres",))
    assert [t.name for t in filtered] == ["postgres__query"]


def test_select_specs_prefers_explicit_tool_names():
    specs = [_tool("postgres__query"), _tool("sandbox__execute_python")]
    selected = _select_specs(specs, ("postgres",), ("sandbox__execute_python",))
    assert [s.name for s in selected] == ["sandbox__execute_python"]


def test_select_specs_fails_closed_without_names_or_prefixes(monkeypatch, caplog):
    """CE-9: unset must not mean every native and extra tool."""
    monkeypatch.delenv("MCP_INJECT_ALLOW_ALL", raising=False)
    specs = [_tool("postgres__query"), _tool("acme__create_ticket")]
    assert _select_specs(specs, (), ()) == []
    assert "MCP_INJECT_ALLOW_ALL" in caplog.text


def test_select_specs_allow_all_is_explicit_opt_in(monkeypatch):
    specs = [_tool("postgres__query"), _tool("acme__create_ticket")]
    monkeypatch.setenv("MCP_INJECT_ALLOW_ALL", "true")
    assert [s.name for s in _select_specs(specs, (), ())] == ["postgres__query", "acme__create_ticket"]
    monkeypatch.setenv("MCP_INJECT_ALLOW_ALL", "false")
    assert _select_specs(specs, (), ()) == []
