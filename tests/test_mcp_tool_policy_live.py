"""Live CE-9 (S-71 deny, S-72 rate limit, S-73 audit metadata) on the unified MCP gateway.

Tests read the installed overlay from env; they never set chart values:
- MCP_POLICY_DENY_TOOL: an agent-visible tool name in workspace.tools.policy.deny
- MCP_POLICY_KEEP_TOOL: optional tool that must stay listed next to the denied one
- ZELKOR_MCP_RATE_LIMIT_PER_MINUTE: workspace.tools.policy.rateLimit.callsPerMinute (keep it small)
- MCP_POLICY_RATE_TOOL / MCP_AUDIT_TOOL: the tool to burst / audit (defaults are the native
  Postgres tools; a perimeter install has only its gateway tool, e.g. aigateway__call)
- MCP_POLICY_TOOL_ARGS: JSON arguments for those calls; "{canary}" is replaced by the S-73 canary
"""
from __future__ import annotations

import json
import os
import subprocess
import time
import uuid

import pytest

from tests.helpers.kube import kubectl_cmd
from tests.helpers.mcp_client import MCPGatewayClient

RATE_TOOL = os.environ.get("MCP_POLICY_RATE_TOOL", "postgres__list_tables")
AUDIT_TOOL = os.environ.get("MCP_AUDIT_TOOL", "postgres__query")


def _args(default: dict, canary: str = "") -> dict:
    raw = os.environ.get("MCP_POLICY_TOOL_ARGS", "").strip()
    if not raw:
        return json.loads(json.dumps(default).replace("{canary}", canary))
    return json.loads(raw.replace("{canary}", canary))


def _client(tenant: str = "tenant_a") -> MCPGatewayClient:
    return MCPGatewayClient(tenant)


def _names(client: MCPGatewayClient) -> list[str]:
    try:
        return [t.get("name") for t in client.list_tools()]
    except ConnectionError as exc:
        pytest.skip(str(exc))


def test_s71_denied_tool_hidden_and_rejected_at_gateway():
    denied = os.environ.get("MCP_POLICY_DENY_TOOL", "").strip()
    if not denied:
        pytest.skip("MCP_POLICY_DENY_TOOL not set (no workspace.tools.policy.deny on this install)")
    client = _client()
    names = _names(client)
    assert denied not in names, names
    keep = os.environ.get("MCP_POLICY_KEEP_TOOL", "").strip()
    if keep:
        assert keep in names, f"deny must not hide the rest: {names}"
    with pytest.raises(Exception):
        client.call_tool(denied, {})


def test_s72_rate_limit_per_tenant_and_tool():
    raw = os.environ.get("ZELKOR_MCP_RATE_LIMIT_PER_MINUTE", "").strip()
    if not raw:
        pytest.skip("ZELKOR_MCP_RATE_LIMIT_PER_MINUTE not set (lab overlay uses a high cap)")
    limit = int(raw)
    if limit < 1 or limit > 20:
        pytest.skip("ZELKOR_MCP_RATE_LIMIT_PER_MINUTE must be 1..20 for a live burst")
    a = _client("tenant_a")
    if RATE_TOOL not in _names(a):
        pytest.skip(f"{RATE_TOOL} not on this gateway")
    errors: list[str] = []
    for _ in range(limit + 1):
        try:
            a.call_tool(RATE_TOOL, _args({}))
        except Exception as exc:  # noqa: BLE001 — collect the tool error text
            errors.append(str(exc))
    assert any("rate limit exceeded" in e for e in errors), errors
    # Another tenant has its own bucket.
    _client("tenant_b").call_tool(RATE_TOOL, _args({}))


def test_s73_audit_record_has_metadata_and_no_arguments():
    canary = f"ZELKOR-ARG-CANARY-{uuid.uuid4().hex[:8]}"
    client = _client()
    if AUDIT_TOOL not in _names(client):
        pytest.skip(f"{AUDIT_TOOL} not on this gateway")
    try:
        client.call_tool(AUDIT_TOOL, _args({"sql": "SELECT 1 /* {canary} */"}, canary))
    except Exception:  # noqa: BLE001 — a failed call is still audited
        pass
    time.sleep(2)
    release = os.environ.get("ZELKOR_RELEASE", "zelkor-platform")
    backend, short = AUDIT_TOOL.split("__", 1)  # {backend}__{tool} -> the backend's Deployment logs
    cmd = kubectl_cmd("logs", f"deploy/{release}-mcp-{backend}", "--since=2m")
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=False)
    except FileNotFoundError:
        pytest.skip("kubectl not available")
    if proc.returncode != 0:
        pytest.skip(f"cannot read MCP logs: {proc.stderr.strip()[:200]}")
    assert canary not in proc.stdout, "tool arguments leaked into MCP logs (P11)"
    records = []
    for line in proc.stdout.splitlines():
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if rec.get("event") == "tools_call" and rec.get("tool") == short:
            records.append(rec)
    assert records, f"no tools_call audit record for {short}"
    rec = records[-1]
    for key in ("tenant_id", "status", "elapsed_s", "request_bytes", "response_bytes"):
        assert key in rec, rec
    assert rec["status"] in {"ok", "error", "denied", "rate_limited"}
