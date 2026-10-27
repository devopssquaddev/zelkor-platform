"""CE-9 Helm render: workspace.tools.policy (deny rules, backend mirror, rate limit) — no cluster."""
from __future__ import annotations

from tests.test_helm_mcproute import _OBJECT_SETS, _mcproute
from tests.test_helm_values_schema import _docs, _helm

NATIVE_DEPLOYMENTS = {
    f"zelkor-platform-mcp-{b}" for b in ("postgres", "qdrant", "sandbox", "aigateway", "object")
}
TENANT_ALLOW_PREFIX = "has(request.auth.jwt.claims."
ACME = (
    "--set", "workspace.tools.extraBackends[0].name=acme",
    "--set", "workspace.tools.extraBackends[0].service.name=acme-mcp",
    "--set", "workspace.tools.extraBackends[0].service.port=8080",
)


def _deny(*entries: str) -> tuple[str, ...]:
    out: list[str] = []
    for i, entry in enumerate(entries):
        out += ["--set-string", f"workspace.tools.policy.deny[{i}]={entry}"]
    return tuple(out)


def _rules(*extra: str) -> list[dict]:
    r = _helm(*extra)
    assert r.returncode == 0, r.stderr
    return _mcproute(_docs(r.stdout))["spec"]["securityPolicy"]["authorization"]["rules"]


def _env(*extra: str) -> dict[str, dict[str, str]]:
    r = _helm(*_OBJECT_SETS, *extra)
    assert r.returncode == 0, r.stderr
    out = {}
    for d in _docs(r.stdout):
        if not d or d.get("kind") != "Deployment" or d["metadata"]["name"] not in NATIVE_DEPLOYMENTS:
            continue
        for c in d["spec"]["template"]["spec"]["containers"]:
            out[d["metadata"]["name"]] = {e["name"]: e.get("value") for e in c.get("env") or []}
    return out


def test_default_has_only_the_tenant_allow_rule():
    rules = _rules()
    assert len(rules) == 1
    assert rules[0]["cel"].startswith(TENANT_ALLOW_PREFIX)
    assert rules[0].get("action", "Allow") == "Allow"


def test_exact_names_render_as_target_tools_deny_before_allow():
    rules = _rules(*_deny("object__delete", "qdrant__upsert_document"))
    assert rules[0]["action"] == "Deny"
    assert rules[0]["target"]["tools"] == [
        {"backend": "object", "tool": "delete"},
        {"backend": "qdrant", "tool": "upsert_document"},
    ]
    assert "cel" not in rules[0]
    assert rules[-1]["cel"].startswith(TENANT_ALLOW_PREFIX)


def test_prefixes_render_as_null_safe_cel_deny():
    rules = _rules(*_deny("object__write*", "sandbox__*"))
    deny = [r for r in rules if r.get("action") == "Deny"]
    assert len(deny) == 1
    cel = deny[0]["cel"]
    assert cel.startswith('request.mcp.method == "tools/call" && (')
    assert '(request.mcp.backend == "object" && request.mcp.tool.startsWith("write"))' in cel
    assert 'request.mcp.backend == "sandbox"' in cel
    assert rules.index(deny[0]) < len(rules) - 1


def test_mixed_entries_render_both_deny_rules_first():
    rules = _rules(*_deny("object__delete", "object__write*"))
    assert [r.get("action") for r in rules] == ["Deny", "Deny", None]


def test_extra_backend_names_are_denied_at_envoy():
    rules = _rules(*ACME, *_deny("acme__create_ticket"))
    assert rules[0]["target"]["tools"] == [{"backend": "acme", "tool": "create_ticket"}]


def test_backends_mirror_their_own_bare_deny_patterns():
    env = _env(*_deny("object__delete", "object__write*", "qdrant__*", "acme__x"))
    assert env["zelkor-platform-mcp-object"]["MCP_DENY_TOOLS"] == "delete,write*"
    assert env["zelkor-platform-mcp-qdrant"]["MCP_DENY_TOOLS"] == "*"
    assert env["zelkor-platform-mcp-postgres"]["MCP_DENY_TOOLS"] == ""


def test_rate_limit_default_60_and_overlay_and_off():
    env = _env()
    assert set(env) == NATIVE_DEPLOYMENTS
    for name, values in env.items():
        assert values["MCP_RATE_LIMIT_PER_MINUTE"] == "60", name
    env = _env("--set", "workspace.tools.policy.rateLimit.callsPerMinute=5")
    assert {v["MCP_RATE_LIMIT_PER_MINUTE"] for v in env.values()} == {"5"}
    env = _env("--set", "workspace.tools.policy.rateLimit.enabled=false")
    assert {v["MCP_RATE_LIMIT_PER_MINUTE"] for v in env.values()} == {"0"}


def test_invalid_deny_entries_fail_render():
    for bad in ("delete", "object__", "Object__x", "object__a*b", "__x"):
        r = _helm(*_deny(bad))
        assert r.returncode != 0, bad
        # Template fail names the key; helm >= 3.18 schema errors use a JSON pointer.
        assert (
            "workspace.tools.policy.deny" in r.stderr or "/workspace/tools/policy/deny" in r.stderr
        ), (bad, r.stderr)


def test_rate_limit_must_be_positive_when_enabled():
    r = _helm("--set", "workspace.tools.policy.rateLimit.callsPerMinute=0")
    assert r.returncode != 0
    assert "callsPerMinute" in r.stderr


def test_extra_tool_selector_accepts_exclude():
    r = _helm(
        *ACME,
        "--set", "workspace.tools.extraBackends[0].toolSelector.exclude[0]=delete_all",
        "--set", "workspace.tools.extraBackends[0].toolSelector.excludeRegex[0]=^write_.*",
    )
    assert r.returncode == 0, r.stderr
    route = _mcproute(_docs(r.stdout))
    (acme,) = [b for b in route["spec"]["backendRefs"] if b["name"] == "acme"]
    assert acme["toolSelector"] == {"exclude": ["delete_all"], "excludeRegex": ["^write_.*"]}


def _agent_env(*extra: str) -> dict[str, str]:
    from tests.test_agent_health_probes import _docs as _adocs, _helm_agent

    r = _helm_agent(*extra)
    assert r.returncode == 0, r.stderr
    (deploy,) = [d for d in _adocs(r.stdout) if d and d.get("kind") == "Deployment"]
    return {e["name"]: e.get("value") for c in deploy["spec"]["template"]["spec"]["containers"] for e in c.get("env") or []}


def test_agent_chart_mcp_inject_fails_closed_by_default():
    assert _agent_env()["MCP_INJECT_ALLOW_ALL"] == "false"
    assert _agent_env("--set", "platform.mcpInjectAllowAll=true")["MCP_INJECT_ALLOW_ALL"] == "true"


def _envoyproxy(*extra: str) -> dict | None:
    r = _helm(*extra)
    assert r.returncode == 0, r.stderr
    eps = [d for d in _docs(r.stdout) if d and d.get("kind") == "EnvoyProxy"]
    return eps[0] if eps else None


def test_mcp_access_log_metadata_only_and_default_log_kept():
    ep = _envoyproxy()
    assert ep is not None
    settings = ep["spec"]["telemetry"]["accessLog"]["settings"]
    default, mcp = settings
    assert "format" not in default  # EG default JSON format for every other path
    assert default["matches"] == ["!request.path.startsWith('/mcp')"]
    assert mcp["matches"] == ["request.path.startsWith('/mcp')"]
    fields = mcp["format"]["json"]
    for key in ("mcp_method", "mcp_backend", "mcp_tool_name", "tenant_id", "response_code", "duration_ms"):
        assert key in fields
    assert "io.envoy.ai_gateway:mcp_tool_name" in fields["mcp_tool_name"]
    joined = " ".join(fields.values()).upper()
    for forbidden in ("BODY", "AUTHORIZATION", "PARAMS"):  # P11: metadata only
        assert forbidden not in joined


def test_mcp_access_log_absent_when_tools_disabled():
    ep = _envoyproxy("--set", "workspace.tools.enabled=false")
    assert ep is None or "telemetry" not in ep["spec"]
