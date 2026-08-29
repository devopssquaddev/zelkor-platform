"""Auto-loaded Mode B MCP tool injection for the Zelkor Aegra runtime image."""
import os

if os.getenv("MCP_INJECT_ENABLED", "").strip().lower() in ("1", "true", "yes", "on"):
    try:
        from mcp_inject import patch_langgraph
        patch_langgraph()
    except Exception:
        pass
