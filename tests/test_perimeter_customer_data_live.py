"""Live: tenants stay isolated over a customer's existing databases.

Two ways data reaches an agent, both through the MCP gateway:
  - Zelkor's data tools (`postgres__*`, `qdrant__*`; perimeter.dataTools on a perimeter) verify the
    caller's JWT and scope every query to that tenant (P5 / P6): each tenant sees only its markers.
  - A customer's own third-party server registered as an extra (CUSTOMER_EXTRA_PREFIX, default
    `crm`) gets the gateway's apiKey and X-Tenant-ID but no JWT; isolation inside it is that
    server's job. A tenant-unaware server returns every tenant's rows: asserted and recorded, so a
    change in that boundary is visible.

Lab facts come from env (table, markers); each part skips when the install does not route that
tool (contract MCP_BACKENDS).
"""
from __future__ import annotations

import json
import os

import pytest

from tests.helpers.kube import platform_contract
from tests.helpers.mcp_client import MCPGatewayClient

TABLE = os.environ.get("CUSTOMER_DATA_TABLE", "portfolios")
MARK = {"tenant_a": os.environ.get("CUSTOMER_MARKER_A", "CRM-A-"),
        "tenant_b": os.environ.get("CUSTOMER_MARKER_B", "CRM-B-")}
DOC_MARK = {"tenant_a": "DOC-A-", "tenant_b": "DOC-B-"}
EXTRA = os.environ.get("CUSTOMER_EXTRA_PREFIX", "crm").strip()
EXTRA_SQL = os.environ.get("CUSTOMER_EXTRA_SQL", "select tenant_id, contact from crm_contacts")
EXTRA_MARK = {"tenant_a": "CONTACT-A-", "tenant_b": "CONTACT-B-"}


def _backends() -> set[str]:
    raw = platform_contract(os.environ.get("ZELKOR_PLATFORM_NAMESPACE", "zelkor")).get("MCP_BACKENDS", "")
    return {b.strip() for b in raw.split(",") if b.strip()}


def _need(backend: str) -> None:
    if backend not in _backends():
        pytest.skip(f"install does not route {backend}__* (contract MCP_BACKENDS)")


def _blob(result) -> str:
    return result if isinstance(result, str) else json.dumps(result, default=str)


@pytest.mark.parametrize("tenant,other", [("tenant_a", "tenant_b"), ("tenant_b", "tenant_a")])
def test_postgres_tool_returns_only_the_callers_rows(tenant, other):
    _need("postgres")
    out = _blob(MCPGatewayClient(tenant).call_tool("postgres__query",
                                                   {"sql": f"select account_number from {TABLE}"}))
    assert MARK[tenant] in out, f"positive control: {tenant} must see its own rows: {out[:300]}"
    assert MARK[other] not in out, f"{tenant} saw {other}'s rows: {out[:300]}"


def test_postgres_tool_refuses_switching_the_session_tenant():
    _need("postgres")
    client = MCPGatewayClient("tenant_b")
    for sql in (f"select set_config('app.current_tenant', 'tenant_a', true), account_number from {TABLE}",
                f"select account_number from {TABLE} where tenant_id = 'tenant_a'"):
        try:
            out = _blob(client.call_tool("postgres__query", {"sql": sql}))
        except Exception as exc:  # refused is fine
            out = repr(exc)
        assert MARK["tenant_a"] not in out, (sql, out[:300])


@pytest.mark.parametrize("tenant,other", [("tenant_a", "tenant_b"), ("tenant_b", "tenant_a")])
def test_qdrant_tool_returns_only_the_callers_documents(tenant, other):
    _need("qdrant")
    out = _blob(MCPGatewayClient(tenant).call_tool("qdrant__search_documents",
                                                   {"query": "travel policy", "limit": 10}))
    assert DOC_MARK[tenant] in out, f"positive control: {tenant} must see its own documents: {out[:300]}"
    assert DOC_MARK[other] not in out, f"{tenant} saw {other}'s documents: {out[:300]}"


def test_tenant_unaware_extra_isolation_is_the_backends_job():
    """Documented CE boundary: the platform guarantees who is calling (X-Tenant-ID), not what a
    third-party server does with it. A tenant-unaware server shows every tenant's rows."""
    _need(EXTRA)
    out = _blob(MCPGatewayClient("tenant_b").call_tool(f"{EXTRA}__execute_sql", {"sql": EXTRA_SQL}))
    assert EXTRA_MARK["tenant_b"] in out, out[:300]
    assert EXTRA_MARK["tenant_a"] in out, (
        "the third-party server now scopes by tenant: update this boundary record", out[:300])
