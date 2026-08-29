"""Unit tests for Mode B MCP tool binder (no cluster)."""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

pytest.importorskip("langchain_core")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "images" / "aegra"))

from mcp_inject import langchain_tools, list_mcp_tools  # noqa: E402


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
