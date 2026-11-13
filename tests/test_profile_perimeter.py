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


def test_unknown_profile_is_rejected():
    proc = _helm("-f", str(LOCAL_PERIMETER), "--set", "profile=bogus")
    assert proc.returncode != 0


def test_default_profile_still_renders_datastores():
    docs = _docs(_helm("-f", str(LOCAL_FAST)).stdout)
    assert _named(docs, "StatefulSet", "postgresql") is not None
