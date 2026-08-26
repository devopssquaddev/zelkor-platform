"""
Zelkor postgres MCP security wrapper (CE).
Exposes MCP tools aligned with @modelcontextprotocol/server-postgres; enforces tenant_id in queries.
"""
import os
import re
import sys
from datetime import date, datetime
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.mcp_server import MCPToolHandler, run_mcp_server
from common.tenant import extract_tenant

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    psycopg2 = None
    RealDictCursor = None

DATABASE_URL = os.getenv(
    "POSTGRES_MCP_URL",
    "postgresql://zelkor:zelkor-dev-password@zelkor-platform-postgresql:5432/finserve",
)


def _serialize_value(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _serialize_row(row):
    return {key: _serialize_value(val) for key, val in row.items()}


class PostgresMCPServer(MCPToolHandler):
    def list_tools(self):
        return [
            {
                "name": "query",
                "description": "Execute a read-only SQL query against PostgreSQL (tenant-scoped)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "sql": {"type": "string"},
                        "tenant_id": {"type": "string"},
                    },
                    "required": ["sql", "tenant_id"],
                },
            }
        ]

    def call_tool(self, name: str, arguments: dict, tenant_id: str):
        if name != "query":
            raise ValueError(f"Unknown tool: {name}")

        sql = (arguments.get("sql") or "").strip()
        arg_tenant = arguments.get("tenant_id")
        if not arg_tenant or arg_tenant != tenant_id:
            raise PermissionError(f"tenant_id mismatch: header={tenant_id}, arg={arg_tenant}")

        if not sql.lower().startswith("select"):
            raise PermissionError("Only SELECT queries are permitted in CE")

        if psycopg2 is None:
            return {"rows": [], "error": "psycopg2 not available"}

        conn = psycopg2.connect(DATABASE_URL)
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if "tenant_id" not in sql.lower():
                    raise PermissionError("SQL must reference tenant_id filter")
                cur.execute(sql, (tenant_id,))
                rows = [_serialize_row(dict(r)) for r in cur.fetchall()]
                return {"rows": rows, "count": len(rows)}
        finally:
            conn.close()


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    run_mcp_server(PostgresMCPServer(), extract_tenant, port=int(os.getenv("PORT", "8080")))
