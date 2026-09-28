"""FinServe demo: bind named MCP tools per run (no import-time tools/list)."""
from __future__ import annotations

import os


MCP_INJECT_PREFIXES = ("__finserve_no_auto_inject__",)


def single_mcp_tool(name: str):
    from mcp_inject import defer_named_mcp_tool

    return defer_named_mcp_tool(name)


def tools_from_env():
    raw = os.getenv("MCP_INJECT_TOOLS", "").strip()
    if not raw:
        return []
    return [single_mcp_tool(n.strip()) for n in raw.split(",") if n.strip()]
