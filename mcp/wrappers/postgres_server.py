"""Zelkor postgres MCP security wrapper (CE).

Thin first-party tools: query, list_tables, get_schema. Tenant identity
comes from the request auth header. SET LOCAL app.current_tenant is
applied on the same transaction Zelkor opens.
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

DATABASE_URL = os.getenv("POSTGRES_MCP_URL", "")

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_CATALOG_SCHEMAS = frozenset({"pg_catalog", "information_schema", "pg_toast"})

LIST_TABLES_SQL = """
SELECT n.nspname AS schema, c.relname AS name
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'v', 'm', 'p')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
  AND has_table_privilege(c.oid, 'SELECT')
ORDER BY 1, 2
"""

GET_SCHEMA_SQL = """
SELECT a.attname AS column_name,
       pg_catalog.format_type(a.atttypid, a.atttypmod) AS data_type,
       NOT a.attnotnull AS is_nullable
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_attribute a ON a.attrelid = c.oid
WHERE c.relkind IN ('r', 'v', 'm', 'p')
  AND a.attnum > 0
  AND NOT a.attisdropped
  AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
  AND n.nspname = %s
  AND c.relname = %s
  AND has_table_privilege(c.oid, 'SELECT')
ORDER BY a.attnum
"""


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


_DOLLAR_PLACEHOLDER = re.compile(r"\$(\d+)")


def _normalize_placeholders(sql: str) -> str:
    """Accept Postgres $1-style binds from models; psycopg2 uses %s."""
    return _DOLLAR_PLACEHOLDER.sub("%s", sql)


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


def _assert_tenant(arguments: dict, tenant_id: str) -> None:
    arg_tenant = arguments.get("tenant_id")
    if not arg_tenant or arg_tenant != tenant_id:
        raise PermissionError(f"tenant_id mismatch: header={tenant_id}, arg={arg_tenant}")


def _is_catalog_schema(schema: str) -> bool:
    lowered = schema.lower()
    return lowered in _CATALOG_SCHEMAS or lowered.startswith("pg_")


def _split_relation(name: str) -> tuple:
    raw = (name or "").strip()
    if not raw:
        raise PermissionError("relation name is required")
    if "." in raw:
        schema, table = raw.split(".", 1)
    else:
        schema, table = "public", raw
    if not _IDENT.match(schema) or not _IDENT.match(table):
        raise PermissionError("relation name must be a simple identifier")
    if _is_catalog_schema(schema):
        raise PermissionError(f"unknown or unauthorized relation: {schema}.{table}")
    return schema, table


def _with_tenant_txn(tenant_id: str, fn):
    if psycopg2 is None:
        return {"error": "psycopg2 not available"}
    conn = psycopg2.connect(DATABASE_URL)
    try:
        conn.autocommit = False
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            try:
                cur.execute("SET LOCAL app.current_tenant = %s", (tenant_id,))
            except Exception:
                conn.rollback()
            result = fn(cur)
            conn.commit()
            return result
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


class PostgresMCPServer(MCPToolHandler):
    def list_tools(self):
        return [
            {
                "name": "query",
                "description": (
                    "Execute a read-only SQL query against PostgreSQL. "
                    "tenant_id must match the authenticated caller. "
                    "Optional params are bound to %s or $1-style placeholders."
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
            },
            {
                "name": "list_tables",
                "description": (
                    "List relation names the connected role can SELECT. "
                    "Filtered by grants and search_path; no catalog dump. "
                    "tenant_id must match the authenticated caller."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {"tenant_id": {"type": "string"}},
                    "required": ["tenant_id"],
                },
            },
            {
                "name": "get_schema",
                "description": (
                    "Columns and types for one relation the role can SELECT. "
                    "Rejects unknown or unauthorized names. "
                    "tenant_id must match the authenticated caller."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "tenant_id": {"type": "string"},
                    },
                    "required": ["name", "tenant_id"],
                },
            },
        ]

    def call_tool(self, name: str, arguments: dict, tenant_id: str):
        _assert_tenant(arguments, tenant_id)
        if name == "query":
            return self._query(arguments, tenant_id)
        if name == "list_tables":
            return self._list_tables(tenant_id)
        if name == "get_schema":
            return self._get_schema(arguments, tenant_id)
        raise ValueError(f"Unknown tool: {name}")

    def _query(self, arguments: dict, tenant_id: str):
        sql = _normalize_placeholders(_assert_read_only(arguments.get("sql") or ""))
        bind = _bind_params(sql, arguments, tenant_id)

        def _run(cur):
            if bind is None:
                cur.execute(sql)
            else:
                cur.execute(sql, bind)
            rows = [_serialize_row(dict(r)) for r in cur.fetchall()]
            return {"rows": rows, "count": len(rows)}

        return _with_tenant_txn(tenant_id, _run)

    def _list_tables(self, tenant_id: str):
        def _run(cur):
            cur.execute(LIST_TABLES_SQL)
            tables = [_serialize_row(dict(r)) for r in cur.fetchall()]
            return {"tables": tables, "count": len(tables)}

        return _with_tenant_txn(tenant_id, _run)

    def _get_schema(self, arguments: dict, tenant_id: str):
        schema, table = _split_relation(arguments.get("name") or "")

        def _run(cur):
            cur.execute(GET_SCHEMA_SQL, (schema, table))
            columns = [_serialize_row(dict(r)) for r in cur.fetchall()]
            if not columns:
                raise PermissionError(f"unknown or unauthorized relation: {schema}.{table}")
            return {
                "name": f"{schema}.{table}",
                "columns": columns,
                "count": len(columns),
            }

        return _with_tenant_txn(tenant_id, _run)


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    run_mcp_server(PostgresMCPServer(), extract_tenant, port=int(os.getenv("PORT", "8080")))
