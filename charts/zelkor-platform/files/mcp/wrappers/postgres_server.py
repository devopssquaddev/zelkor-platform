"""Zelkor postgres MCP security wrapper (CE).

Read-only SQL against the configured database. Tenant identity comes from
the request auth header. The agent supplies any row filters (CE does not
rewrite SQL). SET LOCAL app.current_tenant is applied so optional RLS
policies can use it.
"""
import os
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

DATABASE_URL = os.getenv("POSTGRES_MCP_URL", "")


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


def _assert_read_only(sql: str) -> str:
    stripped = sql.strip().rstrip(";").strip()
    if not stripped:
        raise PermissionError("SQL must not be empty")
    if ";" in stripped:
        raise PermissionError("Multiple SQL statements are not permitted")
    first = stripped.split(None, 1)[0].lower()
    if first not in ("select", "with"):
        raise PermissionError("Only SELECT queries are permitted")
    return stripped


def _bind_params(sql: str, arguments: dict, tenant_id: str):
    params = arguments.get("params")
    placeholders = sql.count("%s")
    if params is None:
        if placeholders == 0:
            return None
        if placeholders == 1:
            return (tenant_id,)
        raise ValueError("SQL has multiple placeholders; pass a params list")
    if not isinstance(params, (list, tuple)):
        raise ValueError("params must be a list")
    return tuple(params)


class PostgresMCPServer(MCPToolHandler):
    def list_tools(self):
        return [
            {
                "name": "query",
                "description": (
                    "Execute a read-only SQL query against PostgreSQL. "
                    "tenant_id must match the authenticated caller. "
                    "Optional params are bound to %s placeholders."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "sql": {"type": "string"},
                        "tenant_id": {"type": "string"},
                        "params": {
                            "type": "array",
                            "items": {"type": ["string", "number", "boolean", "null"]},
                        },
                    },
                    "required": ["sql", "tenant_id"],
                },
            }
        ]

    def call_tool(self, name: str, arguments: dict, tenant_id: str):
        if name != "query":
            raise ValueError(f"Unknown tool: {name}")

        sql = _assert_read_only(arguments.get("sql") or "")
        arg_tenant = arguments.get("tenant_id")
        if not arg_tenant or arg_tenant != tenant_id:
            raise PermissionError(f"tenant_id mismatch: header={tenant_id}, arg={arg_tenant}")

        if psycopg2 is None:
            return {"rows": [], "error": "psycopg2 not available"}

        bind = _bind_params(sql, arguments, tenant_id)
        conn = psycopg2.connect(DATABASE_URL)
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                try:
                    cur.execute("SET LOCAL app.current_tenant = %s", (tenant_id,))
                except Exception:
                    pass
                if bind is None:
                    cur.execute(sql)
                else:
                    cur.execute(sql, bind)
                rows = [_serialize_row(dict(r)) for r in cur.fetchall()]
                return {"rows": rows, "count": len(rows)}
        finally:
            conn.close()


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    run_mcp_server(PostgresMCPServer(), extract_tenant, port=int(os.getenv("PORT", "8080")))
