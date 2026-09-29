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
