"""FinServe demo: bind a single MCP tool without prefix-wide inject (smaller LLM prompt)."""
from __future__ import annotations

# Block Mode B auto-inject; create_agent passes explicit tools below.
MCP_INJECT_PREFIXES = ("__finserve_no_auto_inject__",)


def single_mcp_tool(name: str):
    from mcp_inject import _load_adapter_tools

    for tool in _load_adapter_tools() or []:
        if getattr(tool, "name", "") == name:
            return tool
    raise RuntimeError(f"MCP tool {name!r} not available")
