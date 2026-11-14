"""CE-15a: profile=perimeter renders the zero-DB egress boundary (offline helm template)."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "charts" / "zelkor-platform"
LOCAL_PERIMETER = ROOT / "profiles" / "values-local-perimeter.yaml"
THIN_PERIMETER = ROOT / "profiles" / "values-perimeter.yaml"
LOCAL_FAST = ROOT / "profiles" / "values-local-fast.yaml"

# A provider credential so the AIGatewayRoute renders; the overlay supplies hosts and signing.
PROVIDER = ("--set", "workspace.models.providers.openai.apiKey=sk-test")

# Workloads that must NOT appear in a zero-DB perimeter (matched against Deployment/StatefulSet names).
ABSENT_WORKLOADS = [
    "postgresql", "clickhouse", "valkey", "qdrant", "seaweedfs",
    "langfuse", "aegra", "nemo",
    "mcp-postgres", "mcp-qdrant", "mcp-sandbox",
]


def _helm(*extra: str) -> subprocess.CompletedProcess[str]:
    cmd = ["helm", "template", "zelkor-platform", str(CHART), "--namespace", "zelkor", *extra]
    return subprocess.run(cmd, check=False, capture_output=True, text=True)


def _docs(rendered: str) -> list[dict]:
    return [d for d in yaml.safe_load_all(rendered) if d]


def _named(docs: list[dict], kind: str, substring: str) -> dict | None:
    for doc in docs:
        if doc.get("kind") == kind and substring in doc.get("metadata", {}).get("name", ""):
            return doc
    return None


def _workload_names(docs: list[dict]) -> set[str]:
    return {
        d["metadata"]["name"]
        for d in docs
        if d.get("kind") in ("Deployment", "StatefulSet")
    }


def test_perimeter_disables_every_stateful_workload():
    proc = _helm("-f", str(LOCAL_PERIMETER), *PROVIDER)
    assert proc.returncode == 0, proc.stderr
    names = _workload_names(_docs(proc.stdout))
    for token in ABSENT_WORKLOADS:
        assert not any(token in n for n in names), f"{token} should not render in perimeter: {names}"


def test_perimeter_keeps_the_boundary():
    docs = _docs(_helm("-f", str(LOCAL_PERIMETER), *PROVIDER).stdout)
    assert _named(docs, "Gateway", "-gateway") is not None
    assert _named(docs, "GatewayClass", "eg") is not None
    assert _named(docs, "MCPRoute", "-mcp") is not None
    assert _named(docs, "Deployment", "mcp-aigateway") is not None
    assert _named(docs, "NetworkPolicy", "default-deny-ingress") is not None
    assert _named(docs, "BackendTrafficPolicy", "aigateway-ratelimit") is not None


def test_perimeter_emits_llm_access_token_log():
    # CE-15a-3: perimeter (Langfuse off) still exposes per-/v1 token usage via the
    # always-on llm_access access log + the route's llmRequestCosts.
    docs = _docs(_helm("-f", str(LOCAL_PERIMETER), *PROVIDER).stdout)
    ep = _named(docs, "EnvoyProxy", "envoy-proxy-config")
    assert ep is not None
    settings = ep["spec"]["telemetry"]["accessLog"]["settings"]
    events = [s.get("format", {}).get("json", {}).get("event") for s in settings]
    assert "llm_access" in events
    route = _named(docs, "AIGatewayRoute", "aigateway-route")
    assert route is not None and route["spec"].get("llmRequestCosts")


OTLP_ENDPOINT = "http://otel-collector.monitoring.svc:4318"


def test_perimeter_otlp_renders_gatewayconfig_bound_to_gateway():
    # CE-15a-3b: opt-in BYO OTLP export — a GatewayConfig points the AI gateway's
    # processor at the collector with gen_ai semconv; the Gateway references it by annotation.
    docs = _docs(_helm("-f", str(LOCAL_PERIMETER), *PROVIDER,
                       "--set", f"platform.telemetry.otlp.endpoint={OTLP_ENDPOINT}").stdout)
    gc = _named(docs, "GatewayConfig", "gateway-config")
    assert gc is not None
    env = {e["name"]: e["value"] for e in gc["spec"]["extProc"]["kubernetes"]["env"]}
    assert env["AI_GATEWAY_TRACING_SEMCONV"] == "gen_ai"
    assert env["OTEL_EXPORTER_OTLP_ENDPOINT"] == OTLP_ENDPOINT
    assert env["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] == "false"
    gw = _named(docs, "Gateway", "-gateway")
    assert gw["metadata"]["annotations"]["aigateway.envoyproxy.io/gateway-config"] == gc["metadata"]["name"]


def test_perimeter_without_otlp_has_no_gatewayconfig():
    docs = _docs(_helm("-f", str(LOCAL_PERIMETER), *PROVIDER).stdout)
    assert _named(docs, "GatewayConfig", "gateway-config") is None


def test_perimeter_otlp_capture_content_is_opt_in():
    docs = _docs(_helm("-f", str(LOCAL_PERIMETER), *PROVIDER,
                       "--set", f"platform.telemetry.otlp.endpoint={OTLP_ENDPOINT}",
                       "--set", "platform.telemetry.otlp.captureContent=true").stdout)
    gc = _named(docs, "GatewayConfig", "gateway-config")
    env = {e["name"]: e["value"] for e in gc["spec"]["extProc"]["kubernetes"]["env"]}
    assert env["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] == "true"


def _relay(*extra: str) -> list[dict]:
    r = _helm("-f", str(LOCAL_PERIMETER), *PROVIDER, *extra)
    assert r.returncode == 0, r.stderr
    return [d for d in _docs(r.stdout)
            if d.get("metadata", {}).get("labels", {}).get("app.kubernetes.io/component") == "otlp-relay"]


def test_perimeter_otlp_relay_routes_agent_traces_through_gateway():
    # Agents export to {release}-otlp (the gateway), never the collector: a plain HTTPRoute on its
    # own hostnames (no AI-gateway host, so no extProc) to a collector Backend, consumer-key auth.
    docs = _relay("--set", f"platform.telemetry.otlp.endpoint={OTLP_ENDPOINT}")
    svc = _named(docs, "Service", "-otlp")
    assert svc["spec"]["type"] == "ExternalName"
    assert svc["metadata"]["name"] == "zelkor-platform-otlp"
    route = _named(docs, "HTTPRoute", "-otlp-route")
    assert route["spec"]["hostnames"] == ["zelkor-platform-otlp", "zelkor-platform-otlp.zelkor.svc.cluster.local"]
    rule = route["spec"]["rules"][0]
    assert rule["matches"] == [{"path": {"type": "Exact", "value": "/v1/traces"}}]
    assert "filters" not in rule
    assert rule["backendRefs"] == [{"group": "gateway.envoyproxy.io", "kind": "Backend",
                                    "name": "zelkor-platform-otlp-collector"}]
    backend = _named(docs, "Backend", "-otlp-collector")
    assert backend["spec"]["endpoints"] == [{"fqdn": {"hostname": "otel-collector.monitoring.svc", "port": 4318}}]
    assert _named(docs, "BackendTLSPolicy", "-otlp") is None
    sp = _named(docs, "SecurityPolicy", "-otlp-caller-auth")
    assert sp["spec"]["targetRefs"][0]["name"] == "zelkor-platform-otlp-route"
    assert sp["spec"]["apiKeyAuth"]["credentialRefs"] == [{"name": "zelkor-platform-ai-gateway-consumer"}]
    assert sp["spec"]["apiKeyAuth"]["sanitize"] is True


def test_perimeter_otlp_relay_https_collector_with_path_and_headers():
    docs = _relay("--set", "platform.telemetry.otlp.endpoint=https://otlp.example.com/otlp",
                  "--set", "platform.telemetry.otlp.headers=x-team=abc\\,Authorization=Basic%20Zm9v")
    backend = _named(docs, "Backend", "-otlp-collector")
    assert backend["spec"]["endpoints"][0]["fqdn"] == {"hostname": "otlp.example.com", "port": 443}
    tls = _named(docs, "BackendTLSPolicy", "-otlp-collector-tls")
    assert tls["spec"]["validation"]["hostname"] == "otlp.example.com"
    filters = {f["type"]: f for f in _named(docs, "HTTPRoute", "-otlp-route")["spec"]["rules"][0]["filters"]}
    assert filters["RequestHeaderModifier"]["requestHeaderModifier"]["set"] == [
        {"name": "x-team", "value": "abc"}, {"name": "Authorization", "value": "Basic Zm9v"}]
    assert filters["URLRewrite"]["urlRewrite"]["path"] == {"type": "ReplaceFullPath",
                                                          "replaceFullPath": "/otlp/v1/traces"}


def test_perimeter_without_otlp_has_no_relay():
    assert _relay() == []


def test_otlp_relay_does_not_share_ai_gateway_host():
    docs = _docs(_helm("-f", str(LOCAL_PERIMETER), *PROVIDER,
                       "--set", f"platform.telemetry.otlp.endpoint={OTLP_ENDPOINT}").stdout)
    ai_hosts = set(_named(docs, "AIGatewayRoute", "-aigateway-route")["spec"]["hostnames"])
    assert ai_hosts.isdisjoint(_named(docs, "HTTPRoute", "-otlp-route")["spec"]["hostnames"])


def test_perimeter_mcproute_defaults_to_deny():
    docs = _docs(_helm("-f", str(LOCAL_PERIMETER), *PROVIDER).stdout)
    route = _named(docs, "MCPRoute", "-mcp")
    assert route is not None
    assert '"defaultAction": "Deny"' in json.dumps(route), route


def test_profile_flag_overrides_a_full_config():
    # The raw --set profile=perimeter must win over a complete (full) overlay — the
    # ArtifactHub one-liner path: strip the stateful planes from an otherwise full install.
    proc = _helm("-f", str(LOCAL_FAST), "--set", "profile=perimeter")
    assert proc.returncode == 0, proc.stderr
    names = _workload_names(_docs(proc.stdout))
    for token in ("postgresql", "langfuse", "aegra"):
        assert not any(token in n for n in names), f"{token} should be stripped: {names}"


def test_thin_overlay_only_sets_profile():
    data = yaml.safe_load(THIN_PERIMETER.read_text())
    assert data == {"profile": "perimeter"}


# The tenant-JWT contract every install must supply (an IdP's JWKS), as on a real cluster.
JWT = ("--set", "platform.tenants.jwt.issuer=https://idp.example",
       "--set", "platform.tenants.jwt.audiences={zelkor}",
       "--set", "platform.tenants.jwt.remoteJwksUri=https://idp.example/jwks",
       "--set", "platform.tenants.jwt.jwksEgressCIDRs={203.0.113.0/24}")


def test_thin_production_overlay_renders_with_its_access_logs():
    # The documented production install (thin overlay, no HA) used to fail: no EnvoyProxy, so no
    # in-cluster dataplane Service — and no llm_access / mcp_access logs, perimeter's observability.
    proc = _helm("-f", str(THIN_PERIMETER), *PROVIDER, *JWT)
    assert proc.returncode == 0, proc.stderr
    ep = _named(_docs(proc.stdout), "EnvoyProxy", "")
    assert ep is not None
    events = {s.get("format", {}).get("json", {}).get("event")
              for s in ep["spec"]["telemetry"]["accessLog"]["settings"]}
    assert {"llm_access", "mcp_access"} <= events


def test_perimeter_on_an_external_gateway_emits_no_envoyproxy():
    # A shared/external Gateway owns its EnvoyProxy; the profile must not force a second one.
    proc = _helm("-f", str(THIN_PERIMETER), *PROVIDER, *JWT,
                 "--set", "workspace.models.inClusterService.targetHost=shared-dataplane.envoy-gateway-system.svc.cluster.local")
    assert proc.returncode == 0, proc.stderr
    assert _named(_docs(proc.stdout), "EnvoyProxy", "") is None


def _contract(docs: list[dict]) -> dict:
    cm = _named(docs, "ConfigMap", "zelkor-platform-contract")
    assert cm is not None
    return cm["data"]


def test_perimeter_contract_publishes_mode_and_omits_absent_components():
    # One mode-neutral contract (ADR 04 v2.1) the CLI and Operator read in both profiles.
    data = _contract(_docs(_helm("-f", str(LOCAL_PERIMETER), *PROVIDER,
                                 "--set", f"platform.telemetry.otlp.endpoint={OTLP_ENDPOINT}").stdout))
    assert data["CONTRACT_VERSION"] == "v2.1"
    assert data["PROFILE"] == "perimeter"
    assert data["RELEASE"] == "zelkor-platform"
    assert data["AGENTS_HOST"] == "agents.localhost"
    assert data["NETWORK_POLICIES"] == "true"  # effective: forced by the profile
    assert data["GATEWAY_NAME"] == "zelkor-platform-gateway" and data["GATEWAY_NAMESPACE"] == "zelkor"
    assert data["TENANT_JWT_CONFIGMAP"] == "zelkor-platform-tenant-jwt"
    assert data["TENANT_JWKS_CONFIGMAP"] == "zelkor-platform-tenant-jwks"  # lab overlay signs locally
    assert data["OTLP_RELAY_SERVICE"] == "zelkor-platform-otlp.zelkor.svc.cluster.local:80"
    for absent in ("AEGRA_FRONTDOOR_SERVICE", "DATABASE_SECRET_REF", "VALKEY_SECRET_REF"):
        assert absent not in data


def test_perimeter_publishes_the_tenant_jwt_contract():
    # No longer Aegra-gated: a Helm-only agent install inherits the issuer in perimeter too.
    cm = _named(_docs(_helm("-f", str(LOCAL_PERIMETER), *PROVIDER).stdout), "ConfigMap", "-tenant-jwt")
    assert cm is not None and cm["metadata"]["name"] == "zelkor-platform-tenant-jwt"
    assert cm["data"]["AUTH_JWT_ISSUER"] == "https://local.zelkor.invalid"


def test_remote_jwks_publishes_no_jwks_configmap_in_the_contract():
    data = _contract(_docs(_helm("-f", str(THIN_PERIMETER), *PROVIDER, *JWT).stdout))
    assert "TENANT_JWKS_CONFIGMAP" not in data
    assert data["TENANT_JWT_CONFIGMAP"] == "zelkor-platform-tenant-jwt"


def _names(docs: list[dict], kind: str) -> set[str]:
    return {d["metadata"]["name"] for d in docs if d.get("kind") == kind}


def test_perimeter_renders_no_policies_or_secrets_for_absent_components():
    # A policy or Secret is rendered for a component only when that component exists.
    docs = _docs(_helm("-f", str(LOCAL_PERIMETER), *PROVIDER).stdout)
    assert _names(docs, "NetworkPolicy") == {
        "zelkor-platform-default-deny-ingress", "zelkor-platform-agent-egress",
        "zelkor-platform-mcp-aigateway-egress"}
    assert _names(docs, "Secret") == {"zelkor-platform-ai-gateway-consumer", "zelkor-platform-openai-api-key"}
    egress = _named(docs, "NetworkPolicy", "-agent-egress")["spec"]["egress"]
    components = {(p.get("podSelector") or {}).get("matchLabels", {}).get("app.kubernetes.io/component")
                  for rule in egress for p in rule.get("to", [])}
    assert not components & {"aegra", "langfuse"}


def test_full_profile_keeps_its_component_policies():
    docs = _docs(_helm("-f", str(ROOT / "profiles" / "values-local.yaml"), *PROVIDER).stdout)  # NPs on
    nps = _names(docs, "NetworkPolicy")
    for name in ("aegra-egress", "mcp-postgres-egress", "postgres-dest-deny", "valkey-dest-deny"):
        assert f"zelkor-platform-{name}" in nps, name
    assert "zelkor-platform-ai-gateway-nemo" in _names(docs, "Secret")



def test_unknown_profile_is_rejected():
    proc = _helm("-f", str(LOCAL_PERIMETER), "--set", "profile=bogus")
    assert proc.returncode != 0


def test_default_profile_still_renders_datastores():
    docs = _docs(_helm("-f", str(LOCAL_FAST)).stdout)
    assert _named(docs, "StatefulSet", "postgresql") is not None


def test_production_perimeter_is_the_production_overlay_plus_the_profile():
    # Same overlays as a full production install, plus the one-line perimeter overlay.
    proc = _helm("-f", str(ROOT / "profiles" / "values-production.yaml"), "-f", str(THIN_PERIMETER),
                 *PROVIDER, *JWT)
    assert proc.returncode == 0, proc.stderr
    docs = _docs(proc.stdout)
    assert _workload_names(docs) == {"zelkor-platform-mcp-aigateway"}
    assert _named(docs, "EnvoyProxy", "") is not None


OTLP = ("--set", "platform.telemetry.otlp.endpoint=http://otel-collector.monitoring.svc:4318")


def _optin(*flags: str) -> list[dict]:
    proc = _helm("-f", str(LOCAL_PERIMETER), *PROVIDER, *OTLP, *flags)
    assert proc.returncode == 0, proc.stderr
    return _docs(proc.stdout)


def test_opt_ins_add_only_their_own_components():
    base = _optin()
    guard = _optin("--set", "perimeter.guardrails=true")
    sandbox = _optin("--set", "perimeter.sandbox=true")
    assert _workload_names(guard) - _workload_names(base) == {"zelkor-platform-nemo"}
    added = _workload_names(sandbox) - _workload_names(base)
    assert "zelkor-platform-mcp-sandbox" in added and all("mcp-sandbox" in n for n in added)
    # datastores, Langfuse, Aegra and the data-plane MCP stay off with both opt-ins
    both = _workload_names(_optin("--set", "perimeter.guardrails=true", "--set", "perimeter.sandbox=true"))
    for token in ("postgresql", "clickhouse", "valkey", "qdrant", "seaweedfs", "langfuse", "aegra",
                  "mcp-postgres", "mcp-qdrant", "mcp-object"):
        assert not any(token in n for n in both), (token, both)
    assert "zelkor-platform-ai-gateway-nemo" in _names(guard, "Secret") - _names(base, "Secret")
    assert {"zelkor-platform-sandbox-worker-ingress", "zelkor-platform-sandbox-worker-egress"} <= \
        _names(sandbox, "NetworkPolicy") - _names(base, "NetworkPolicy")


def test_opt_ins_are_ignored_by_the_full_profile_defaults():
    # the full profile ships NeMo and the sandbox regardless of perimeter.*
    names = _workload_names(_docs(_helm("-f", str(ROOT / "profiles" / "values-local.yaml"), *PROVIDER,
                                        "--set", "perimeter.guardrails=false").stdout))
    assert any("nemo" in n for n in names) and any("mcp-sandbox" in n for n in names)


def test_perimeter_nemo_exports_through_the_otlp_relay():
    nemo = _named(_optin("--set", "perimeter.guardrails=true"), "Deployment", "-nemo")
    (c,) = [c for c in nemo["spec"]["template"]["spec"]["containers"] if c["name"] == "nemo-guardrails"]
    env = {e["name"]: e.get("value", e.get("valueFrom")) for e in c["env"]}
    assert c["command"] == ["opentelemetry-instrument"]
    assert env["OTEL_EXPORTER_OTLP_ENDPOINT"] == "http://zelkor-platform-otlp.zelkor.svc.cluster.local:80"
    assert env["OTEL_EXPORTER_OTLP_HEADERS"] == "authorization=Bearer%20$(ZELKOR_CONSUMER_KEY)"
    assert env["ZELKOR_CONSUMER_KEY"]["secretKeyRef"] == {"name": "zelkor-platform-ai-gateway-consumer",
                                                           "key": "agents"}
    assert "LANGFUSE_EXTRA_OTLP" not in env and not c.get("envFrom")
    # no OTLP endpoint: NeMo runs without tracing
    plain = _docs(_helm("-f", str(LOCAL_PERIMETER), *PROVIDER, "--set", "perimeter.guardrails=true").stdout)
    (c2,) = [c for c in _named(plain, "Deployment", "-nemo")["spec"]["template"]["spec"]["containers"]
             if c["name"] == "nemo-guardrails"]
    assert c2["command"] == ["python", "/app/boot.py"]


def test_contract_publishes_the_optional_planes():
    assert {k: _contract(_optin()).get(k) for k in ("GUARDRAILS_ENABLED", "SANDBOX_ENABLED")} == \
        {"GUARDRAILS_ENABLED": "false", "SANDBOX_ENABLED": "false"}
    both = _contract(_optin("--set", "perimeter.guardrails=true", "--set", "perimeter.sandbox=true"))
    assert both["GUARDRAILS_ENABLED"] == "true" and both["SANDBOX_ENABLED"] == "true"
    full = _contract(_docs(_helm("-f", str(ROOT / "profiles" / "values-local.yaml"), *PROVIDER).stdout))
    assert full["GUARDRAILS_ENABLED"] == "true" and full["SANDBOX_ENABLED"] == "true"
