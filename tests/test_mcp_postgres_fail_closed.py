"""Postgres MCP must not run queries when SET LOCAL app.current_tenant fails (slice 0)."""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mcp"))

from wrappers.postgres_server import _with_tenant_txn  # noqa: E402


def test_set_local_failure_raises_and_skips_query():
    conn = MagicMock()
    cur = MagicMock()
    cur.execute.side_effect = [RuntimeError("GUC not defined"), AssertionError("query ran")]
    conn.cursor.return_value.__enter__.return_value = cur

    with patch("wrappers.postgres_server.psycopg2") as mock_pg:
        mock_pg.connect.return_value = conn
        with pytest.raises(PermissionError, match="tenant isolation failed"):
            _with_tenant_txn("tenant-a", lambda c: c.execute("SELECT 1"))

    assert cur.execute.call_count == 1
    conn.rollback.assert_called()
