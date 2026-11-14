"""CE-14 zelkor-agent chart: runtime aegra (unchanged) vs a2a / opencode behind zelkor-sidecar (no cluster)."""
from __future__ import annotations

import pytest
import yaml

from tests.test_agent_health_probes import _helm_agent

FORBIDDEN_IN_RUNTIME = {"DATABASE_URL", "REDIS_URL", "LANGFUSE_SECRET_KEY", "LANGFUSE_PUBLIC_KEY",
                        "AUTH_JWKS_PATH", "AUTH_JWKS_URI"}


def _deploy(*extra):
    r = _helm_agent(*extra)
    assert r.returncode == 0, r.stderr
    (d,) = [x for x in yaml.safe_load_all(r.stdout) if x and x.get("kind") == "Deployment"]
    return d["spec"]["template"]["spec"]


def _env(container):
    return {e["name"]: e.get("value") for e in container.get("env") or []}


def _c(spec, name):
    (c,) = [c for c in spec["containers"] if c["name"] == name]
    return c


def test_default_runtime_is_aegra_single_container():
    spec = _deploy()
    assert [c["name"] for c in spec["containers"]] == ["agent"]
    assert "initContainers" not in spec
    assert _env(spec["containers"][0])["DATABASE_URL"]


def test_unknown_runtime_fails():
    r = _helm_agent("--set", "runtime=hermes")
    # the values schema (or, without it, the template guard) refuses it
    assert r.returncode != 0 and ("runtime must be aegra, a2a or opencode" in r.stderr
                                  or 'runtime must be one of the following: "aegra", "a2a", "opencode"' in r.stderr)


@pytest.mark.parametrize("runtime", ["a2a", "opencode"])
def test_sidecar_layout(runtime):
    spec = _deploy("--set", f"runtime={runtime}", "--set", "image.repository=ghcr.io/acme/agent",
                   "--set", "platform.consumerKey=ck-123", "--set", "platform.mcpInjectToolPrefixes=postgres\\,sandbox")
    assert [c["name"] for c in spec["initContainers"]] == ["migrate"]
    assert spec["initContainers"][0]["args"] == ["zelkor_sidecar.migrate"]
    assert [c["name"] for c in spec["containers"]] == ["sidecar", "agent"]

    sidecar, agent = _c(spec, "sidecar"), _c(spec, "agent")
    assert sidecar["image"].startswith("ghcr.io/devopssquaddev/zelkor-sidecar:2.4.4")
    assert sidecar["ports"] == [{"containerPort": 8000, "name": "http"}]
    assert sidecar["readinessProbe"]["httpGet"]["port"] == 8000
    s_env = _env(sidecar)
    assert s_env["ZELKOR_RUNTIME"] == runtime
    assert s_env["ZELKOR_LLM_UPSTREAM"] == "http://zelkor-platform-ai-gateway:80/v1"
    assert s_env["ZELKOR_MCP_UPSTREAM"].endswith("-mcp/mcp")
    assert s_env["ZELKOR_CONSUMER_KEY"] == "ck-123"
    assert s_env["ZELKOR_TOOL_PREFIXES"] == "postgres,sandbox"
    assert s_env["ZELKOR_TOOL_ALLOW_ALL"] == "false"
    assert s_env["ZELKOR_NEMO_TOOLS_NO_STREAM"] == "true"
    assert s_env["DATABASE_URL"]

    assert agent["image"].startswith("ghcr.io/acme/agent:")
    assert "ports" not in agent
    a_env = _env(agent)
    assert a_env["OPENAI_BASE_URL"] == "http://127.0.0.1:8001/run/active/v1"
    assert a_env["MCP_URL"] == "http://127.0.0.1:8001/run/active/mcp"
    assert not FORBIDDEN_IN_RUNTIME & set(a_env)
    assert "ck-123" not in a_env.values()
    assert "envFrom" not in agent

    for c in (sidecar, agent, spec["initContainers"][0]):
        sc = c["securityContext"]
        assert sc["readOnlyRootFilesystem"] is True and sc["runAsNonRoot"] is True
        assert sc["allowPrivilegeEscalation"] is False and sc["capabilities"]["drop"] == ["ALL"]
    assert {v["name"] for v in spec["volumes"]} >= {"sidecar-tmp", "runtime-tmp"}


def test_a2a_northbound_toggle_and_card_url():
    off = _env(_c(_deploy("--set", "runtime=a2a"), "sidecar"))
    assert off["ZELKOR_A2A_ENABLED"] == "false" and "ZELKOR_A2A_PUBLIC_URL" not in off
    on = _env(_c(_deploy("--set", "runtime=a2a", "--set", "sidecar.a2a.enabled=true",
                         "--set", "sharedRoute.host=agents.example.com"), "sidecar"))
    assert on["ZELKOR_A2A_ENABLED"] == "true"
    assert on["ZELKOR_A2A_PUBLIC_URL"] == "https://agents.example.com/a2a?graph_id=demo-graph"


def test_service_and_port_unchanged_for_sidecar_runtimes():
    r = _helm_agent("--set", "runtime=opencode")
    (svc,) = [x for x in yaml.safe_load_all(r.stdout) if x and x.get("kind") == "Service"]
    assert svc["spec"]["ports"][0]["targetPort"] == 8000


def test_mcp_upstream_is_never_double_suffixed():
    """The CLI passes platform.mcpUrl with /mcp already; the sidecar upstream must stay .../mcp."""
    for url in ("http://zelkor-platform-mcp", "http://zelkor-platform-mcp/", "http://zelkor-platform-mcp/mcp"):
        env = _env(_c(_deploy("--set", "runtime=a2a", "--set", f"platform.mcpUrl={url}"), "sidecar"))
        assert env["ZELKOR_MCP_UPSTREAM"] == "http://zelkor-platform-mcp/mcp", url



def _ingress(*extra):
    r = _helm_agent("--set", "security.networkPolicies.enabled=true", *extra)
    assert r.returncode == 0, r.stderr
    (np,) = [x for x in yaml.safe_load_all(r.stdout) if x and x.get("kind") == "NetworkPolicy"
             and x["metadata"]["name"].endswith("-ingress")]
    return np["spec"]["ingress"][0]["from"]


def test_ingress_default_is_gateway_namespace_only():
    assert _ingress() == [{"namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": "envoy-gateway-system"}}}]


def test_egress_only_stateless_sidecar_has_no_db():
    # CE-15a-2 perimeter: stateless sidecar runs DB-less (no migrate, no DATABASE_URL, memory store).
    spec = _deploy("--set", "runtime=a2a", "--set", "sidecar.stateless=true",
                   "--set", "image.repository=ghcr.io/acme/agent")
    assert "initContainers" not in spec
    sidecar = _c(spec, "sidecar")
    s_env = _env(sidecar)
    assert s_env.get("ZELKOR_SIDECAR_STORE") == "memory"
    assert "DATABASE_URL" not in s_env
    # the agent is still wrapped: its egress goes through the sidecar loopback
    assert _env(_c(spec, "agent"))["OPENAI_BASE_URL"] == "http://127.0.0.1:8001/run/active/v1"


PERIMETER = ("--set", "runtime=a2a", "--set", "sidecar.stateless=true",
             "--set", "image.repository=ghcr.io/acme/agent")


def test_sidecar_exports_traces_through_platform_otlp_relay():
    # CE-15a-3: the sidecar posts to the platform's {release}-otlp relay (the gateway) and
    # authenticates with the consumer key; it never holds the collector address or headers.
    spec = _deploy(*PERIMETER, "--set", "platform.otlp=true")
    env = _c(spec, "sidecar")["env"]
    names = [e["name"] for e in env]
    s_env = _env(_c(spec, "sidecar"))
    assert s_env["OTEL_EXPORTER_OTLP_ENDPOINT"] == "http://zelkor-platform-otlp"
    assert s_env["OTEL_EXPORTER_OTLP_HEADERS"] == "authorization=Bearer $(ZELKOR_CONSUMER_KEY)"
    # $(VAR) expansion only sees variables defined earlier in the same container
    assert names.index("ZELKOR_CONSUMER_KEY") < names.index("OTEL_EXPORTER_OTLP_HEADERS")
    assert not any(n.startswith("OTEL_EXPORTER_OTLP") for n in _env(_c(spec, "agent")))


def test_sidecar_otlp_relay_cross_namespace_uses_fqdn():
    spec = _deploy(*PERIMETER, "--set", "platform.otlp=true", "--set", "platform.namespace=zelkor-sys")
    assert _env(_c(spec, "sidecar"))["OTEL_EXPORTER_OTLP_ENDPOINT"] == \
        "http://zelkor-platform-otlp.zelkor-sys.svc.cluster.local"


def test_sidecar_without_otlp_exports_nothing():
    assert "OTEL_EXPORTER_OTLP_ENDPOINT" not in _env(_c(_deploy(*PERIMETER), "sidecar"))


def test_otlp_relay_requires_platform_release():
    r = _helm_agent(*PERIMETER, "--set", "platform.otlp=true", "--set", "platform.releaseName=",
                    "--set", "auth.jwksUri=https://issuer.example/jwks")
    assert r.returncode != 0 and "platform.otlp needs platform.releaseName" in r.stderr


def test_egress_policy_has_no_collector_rule():
    # The relay is the gateway, so no OTLP port or collector CIDR is ever opened.
    r = _helm_agent(*PERIMETER, "--set", "platform.otlp=true", "--set", "security.networkPolicies.enabled=true")
    assert r.returncode == 0, r.stderr
    (np,) = [x for x in yaml.safe_load_all(r.stdout) if x and x.get("kind") == "NetworkPolicy"
             and x["metadata"]["name"].endswith("-egress")]
    ports = {p["port"] for rule in np["spec"]["egress"] for p in rule.get("ports", [])}
    assert not ports & {4317, 4318}
    assert not any("ipBlock" in t for rule in np["spec"]["egress"] for t in rule.get("to", []))


def test_kind_host_network_gateway_cidrs_add_node_ip_blocks_only():
    src = _ingress("--set", "security.networkPolicies.hostNetworkGatewayCIDRs[0]=172.22.0.2/32")
    assert src[1] == {"ipBlock": {"cidr": "172.22.0.2/32"}}
    for bad in ("0.0.0.0/0", "172.22.0.0/16", "10.0.0.1"):
        r = _helm_agent("--set", "security.networkPolicies.enabled=true",
                        "--set", f"security.networkPolicies.hostNetworkGatewayCIDRs[0]={bad}")
        assert r.returncode != 0 and "/32" in r.stderr, bad


def test_stateless_sidecar_cannot_wrap_aegra():
    # Aegra always needs a database; a "stateless" Aegra pod would crash-loop.
    r = _helm_agent("--set", "sidecar.stateless=true", "--set", "runtime=aegra")
    assert r.returncode != 0 and "sidecar.stateless needs a sidecar runtime" in r.stderr


def test_stateless_sidecar_is_single_replica():
    # Runs live in pod memory: a second replica answers 404 for the first one's threads.
    for extra in (("--set", "replicaCount=2"), ("--set", "autoscaling.enabled=true")):
        r = _helm_agent(*PERIMETER, *extra)
        assert r.returncode != 0 and "one replica" in r.stderr, extra
    assert _helm_agent(*PERIMETER, "--set", "replicaCount=1").returncode == 0
