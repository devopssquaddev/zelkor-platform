"""Live: what identity a customer MCP backend (extra) receives through the gateway.

The gateway verifies the caller's JWT and never forwards it; the backend gets the configured
apiKey and the identity headers it asked for (forwardHeaders), set by the gateway from the
verified token. These tests prove a caller cannot forge that header. They use the echo test
server registered as an extra (MCP_IDENTITY_PROBE_PREFIX, default `probe`), which reports the
tenant and Authorization it received. Skip when no such extra is registered.
"""
from __future__ import annotations

import os
import uuid

import pytest

from tests.helpers.mcp_client import MCPGatewayClient

PREFIX = os.environ.get("MCP_IDENTITY_PROBE_PREFIX", "probe").strip() + "__"
TOOL = f"{PREFIX}ping"


def _ping(client: MCPGatewayClient) -> dict:
    try:
        names = [t.get("name") for t in client.list_tools()]
    except ConnectionError as exc:
        pytest.skip(str(exc))
    if TOOL not in names:
        pytest.skip(f"no identity probe extra ({TOOL} not in tools/list)")
    return client.call_tool(TOOL, {})


def test_forged_tenant_header_loses_to_the_verified_token():
    forged = f"forged-{uuid.uuid4().hex[:8]}"
    seen = _ping(MCPGatewayClient("tenant_a", extra_headers={"X-Tenant-ID": forged}))
    assert seen.get("tenant_id") == "tenant_a", seen


def test_backend_gets_the_api_key_never_the_callers_jwt():
    seen = _ping(MCPGatewayClient("tenant_a"))
    assert seen.get("has_authorization") is True, seen  # the gateway's apiKey for this backend
    assert seen.get("authorization_is_jwt") is False, seen


def test_token_without_a_tenant_claim_cannot_carry_a_forged_tenant():
    from tests.helpers.lab_jwt import sign

    forged = f"forged-{uuid.uuid4().hex[:8]}"
    token = sign({"sub": f"user-{uuid.uuid4().hex[:6]}"})
    client = MCPGatewayClient("tenant_a", bearer=token, extra_headers={"X-Tenant-ID": forged})
    try:
        seen = client.call_tool(TOOL, {})
    except Exception as exc:  # refused at the gateway (no tenant claim) is the expected outcome
        assert forged not in repr(exc)
        return
    assert seen.get("tenant_id") != forged, seen
