"""Zelkor sandbox MCP — warm pool orchestrator with execute_python tool."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.mcp_server import MCPToolHandler, run_mcp_server
from common.tenant import extract_tenant
from sandbox.pool_manager import execute_on_worker


class SandboxMCPServer(MCPToolHandler):
    def list_tools(self):
        return [
            {
                "name": "execute_python",
                "description": "Execute Python code in a gVisor-isolated warm pool worker",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string"},
                        "tenant_id": {"type": "string"},
                        "environment": {"type": "string", "enum": ["python-base"]},
                    },
                    "required": ["code", "tenant_id"],
                },
            }
        ]

    def call_tool(self, name: str, arguments: dict, tenant_id: str):
        if name != "execute_python":
            raise ValueError(f"Unknown tool: {name}")

        arg_tenant = arguments.get("tenant_id")
        if not arg_tenant or arg_tenant != tenant_id:
            raise PermissionError(f"tenant_id mismatch: header={tenant_id}, arg={arg_tenant}")

        code = arguments.get("code") or ""
        timeout = int(arguments.get("timeout") or 5)
        return execute_on_worker(code, tenant_id, timeout=timeout)


if __name__ == "__main__":
    run_mcp_server(SandboxMCPServer(), extract_tenant, port=int(os.getenv("PORT", "8080")))
