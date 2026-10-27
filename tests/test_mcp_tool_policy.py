"""CE-9 native MCP tool policy: deny list, per-tenant/tool rate limit, audit metadata (no cluster)."""
import json
import logging
import sys
from pathlib import Path

import anyio
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp"))

from common.mcp_server import MCPToolHandler, run_tool_call  # noqa: E402
from common.tool_policy import RateLimiter, ToolPolicy  # noqa: E402

CANARY = "ZELKOR-ARG-CANARY-7f3e"


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class _Handler(MCPToolHandler):
    def __init__(self) -> None:
        self.calls: list[str] = []

    def list_tools(self):
        return []

    def call_tool(self, name, arguments, tenant_id, limiter=None):
        self.calls.append(name)
        if name == "boom":
            raise RuntimeError("backend exploded")
        return {"ok": True, "echo_len": len(json.dumps(arguments))}


def _call(handler, name, *, tenant="tenant-a", policy=None, rate=None, args=None):
    async def go():
        return await run_tool_call(
            handler,
            name,
            args if args is not None else {"q": CANARY},
            tenant,
            limiter=anyio.CapacityLimiter(4),
            policy=ToolPolicy([]) if policy is None else policy,
            rate=RateLimiter(0) if rate is None else rate,
        )

    return anyio.run(go)


# --- deny -----------------------------------------------------------------


@pytest.mark.parametrize(
    "patterns,name,denied",
    [
        (["delete"], "delete", True),
        (["delete"], "delete_all", False),
        (["write*"], "write_text", True),
        (["write*"], "rewrite", False),
        (["*"], "anything", True),
        ([], "delete", False),
    ],
)
def test_policy_matches_exact_prefix_and_all(patterns, name, denied):
    assert (ToolPolicy(patterns).deny_reason(name) is not None) is denied


def test_policy_from_env(monkeypatch):
    monkeypatch.setenv("MCP_DENY_TOOLS", " delete , write* ,")
    policy = ToolPolicy.from_env()
    assert policy.deny_reason("delete")
    assert policy.deny_reason("write_text")
    assert policy.deny_reason("list") is None


def test_policy_ignores_mcp_hints():
    """A tool advertising readOnlyHint is still denied by name."""
    policy = ToolPolicy(["write_text"])
    assert policy.filter_tools([
        {"name": "write_text", "annotations": {"readOnlyHint": True}},
        {"name": "read_text"},
    ]) == [{"name": "read_text"}]


def test_denied_call_never_dispatches():
    handler = _Handler()
    with pytest.raises(PermissionError, match="denied by workspace.tools.policy.deny"):
        _call(handler, "delete", policy=ToolPolicy(["delete"]))
    assert handler.calls == []


# --- rate limit -----------------------------------------------------------


def test_rate_limit_per_tenant_and_tool():
    clock = _Clock()
    rate = RateLimiter(3, clock=clock)
    assert [rate.allow("a", "t") for _ in range(4)] == [True, True, True, False]
    assert rate.allow("b", "t") is True  # other tenant unaffected
    assert rate.allow("a", "other") is True  # other tool unaffected
    clock.now += 20  # one third of a minute refills one call
    assert rate.allow("a", "t") is True
    assert rate.allow("a", "t") is False


def test_rate_limit_zero_disables():
    rate = RateLimiter(0)
    assert all(rate.allow("a", "t") for _ in range(1000))


def test_rate_limit_bounds_tracked_keys():
    rate = RateLimiter(5, max_keys=10)
    for i in range(50):
        rate.allow(f"tenant-{i}", "t")
    assert len(rate) <= 10


def test_rate_limited_call_never_dispatches():
    handler = _Handler()
    rate = RateLimiter(1)
    _call(handler, "search", rate=rate)
    with pytest.raises(PermissionError, match="rate limit exceeded"):
        _call(handler, "search", rate=rate)
    assert handler.calls == ["search"]


# --- audit ----------------------------------------------------------------


def _audit_records(caplog):
    return [r for r in caplog.records if getattr(r, "event", "") == "tools_call"]


def test_audit_ok_record_has_metadata_and_no_arguments(caplog):
    caplog.set_level(logging.INFO, logger="zelkor-mcp")
    _call(_Handler(), "search")
    (rec,) = _audit_records(caplog)
    assert rec.levelno == logging.INFO
    assert rec.tool == "search"
    assert rec.tenant_id == "tenant-a"
    assert rec.status == "ok"
    assert rec.request_bytes > 0
    assert rec.response_bytes > 0
    assert rec.elapsed_s >= 0
    assert CANARY not in caplog.text


@pytest.mark.parametrize(
    "name,kwargs,status,reason",
    [
        ("delete", {"policy": ToolPolicy(["delete"])}, "denied", "policy"),
        ("boom", {}, "error", ""),
    ],
)
def test_audit_failure_statuses(caplog, name, kwargs, status, reason):
    caplog.set_level(logging.INFO, logger="zelkor-mcp")
    with pytest.raises(Exception):
        _call(_Handler(), name, **kwargs)
    (rec,) = _audit_records(caplog)
    assert rec.status == status
    assert getattr(rec, "deny_reason", "") == reason
    assert CANARY not in caplog.text


def test_audit_rate_limited_status(caplog):
    caplog.set_level(logging.INFO, logger="zelkor-mcp")
    rate = RateLimiter(1)
    _call(_Handler(), "search", rate=rate)
    caplog.clear()
    with pytest.raises(PermissionError):
        _call(_Handler(), "search", rate=rate)
    (rec,) = _audit_records(caplog)
    assert rec.status == "rate_limited"
    assert rec.deny_reason == "rate_limit"


def test_missing_tenant_is_denied_and_audited(caplog):
    caplog.set_level(logging.INFO, logger="zelkor-mcp")
    handler = _Handler()
    with pytest.raises(PermissionError, match="Missing tenant identity"):
        _call(handler, "search", tenant=None)
    assert handler.calls == []
    (rec,) = _audit_records(caplog)
    assert rec.status == "denied"
    assert rec.deny_reason == "no_tenant"


def test_audit_fields_are_json_context_keys():
    sys.path.insert(0, str(ROOT / "images" / "common"))
    from zelkor_logging import _CONTEXT_KEYS

    for key in ("tool", "tenant_id", "elapsed_s", "status", "request_bytes", "response_bytes", "deny_reason"):
        assert key in _CONTEXT_KEYS
