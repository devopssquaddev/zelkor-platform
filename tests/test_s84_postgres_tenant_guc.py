"""S-84: agent SQL cannot switch app.current_tenant inside the MCP transaction.

The tenant GUC is user-settable, so a SELECT that calls set_config() (directly, quoted, behind a
comment, or as dynamic SQL) could re-point RLS at another tenant mid-query. The wrapper rejects such
SQL, runs the transaction READ ONLY, and refuses to return rows if the GUC changed anyway.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mcp"))

from tests.helpers.mcp_client import MCPGatewayClient  # noqa: E402
from wrappers.postgres_server import _assert_read_only, _with_tenant_txn  # noqa: E402

SWITCH = [
    "SELECT * FROM t WHERE set_config('app.current_tenant','other',true) IS NOT NULL",
    "WITH s AS MATERIALIZED (SELECT set_config('app.current_tenant','other',true)) SELECT t.* FROM s, t",
    "SELECT pg_catalog.set_config('app.current_tenant','other',true)",
    'SELECT "set_config"(\'app.current_tenant\',\'other\',true)',
    "SELECT SET_CONFIG ('app.current_tenant','other',true)",
    "SELECT set_config/**/('app.current_tenant','other',true)",
    "SELECT set_config--x\n('app.current_tenant','other',true)",
    'SELECT U&"\\0073et_config"(\'app.current_tenant\',\'other\',true)',
    "SELECT query_to_xml('select se'||'t_config(''app.current_tenant'',''other'',true)', true, true, '')",
    "SELECT * FROM ts_stat('select 1')",
]


@pytest.mark.parametrize("sql", SWITCH)
def test_tenant_switch_sql_is_rejected(sql):
    with pytest.raises(PermissionError, match="not permitted"):
        _assert_read_only(sql)


@pytest.mark.parametrize("sql", [
    "SELECT current_setting('app.current_tenant', true)",
    "SELECT config_set, set_config_note FROM t",
    "SELECT * FROM t WHERE note = 'xml'",
])
def test_ordinary_selects_still_pass(sql):
    assert _assert_read_only(sql) == sql


def _txn(executed, guc_after):
    conn = MagicMock()
    cur = MagicMock()
    cur.execute.side_effect = lambda q, *a: executed.append(q)
    cur.fetchone.return_value = {"current_setting": guc_after}
    conn.cursor.return_value.__enter__.return_value = cur
    return conn


def test_transaction_is_read_only_before_tenant_is_set():
    executed: list = []
    with patch("wrappers.postgres_server.psycopg2") as pg:
        pg.connect.return_value = _txn(executed, "tenant-a")
        assert _with_tenant_txn("tenant-a", lambda c: "rows") == "rows"
    assert executed[0] == "SET TRANSACTION READ ONLY"
    assert executed[1].startswith("SET LOCAL app.current_tenant")


def test_changed_tenant_guc_returns_nothing():
    executed: list = []
    with patch("wrappers.postgres_server.psycopg2") as pg:
        conn = _txn(executed, "tenant-b")
        pg.connect.return_value = conn
        with pytest.raises(PermissionError, match="tenant isolation failed"):
            _with_tenant_txn("tenant-a", lambda c: "other tenant rows")
    conn.rollback.assert_called()
    conn.commit.assert_not_called()


def test_live_set_config_is_rejected():
    """L3: the gateway path refuses the switch for any tenant (schema-agnostic)."""
    client = MCPGatewayClient("tenant_a")
    try:
        with pytest.raises(RuntimeError, match="(?i)not permitted"):
            client.call_tool(
                "postgres__query",
                {"sql": "SELECT set_config('app.current_tenant', 'tenant_b', true)"},
            )
    except ConnectionError as exc:
        pytest.skip(str(exc))
