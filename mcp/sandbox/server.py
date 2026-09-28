"""Zelkor sandbox MCP — warm pool orchestrator with execute_python tool."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.mcp_server import MCPToolHandler, run_mcp_server
from common.tenant import extract_tenant
from sandbox.pool_manager import execute_on_worker

MAX_TIMEOUT = int(os.getenv("SANDBOX_MAX_TIMEOUT_SECONDS", "90"))


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
                        "environment": {"type": "string", "enum": ["python-base"]},
                        "timeout": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": MAX_TIMEOUT,
                        },
                    },
                    "required": ["code"],
                    "additionalProperties": False,
                },
            }
        ]

    def call_tool(self, name: str, arguments: dict, tenant_id: str):
        if name != "execute_python":
            raise ValueError(f"Unknown tool: {name}")

        code = arguments.get("code") or ""
        raw_timeout = arguments.get("timeout")
        timeout = int(raw_timeout) if raw_timeout is not None else 5
        if timeout < 1:
            timeout = 1
        if timeout > MAX_TIMEOUT:
            timeout = MAX_TIMEOUT
        return execute_on_worker(code, tenant_id, timeout=timeout)


if __name__ == "__main__":
    run_mcp_server(SandboxMCPServer(), extract_tenant, port=int(os.getenv("PORT", "8080")))
