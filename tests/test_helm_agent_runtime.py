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
    assert r.returncode != 0 and "runtime must be aegra, a2a or opencode" in r.stderr


@pytest.mark.parametrize("runtime", ["a2a", "opencode"])
def test_sidecar_layout(runtime):
    spec = _deploy("--set", f"runtime={runtime}", "--set", "image.repository=ghcr.io/acme/agent",
                   "--set", "platform.consumerKey=ck-123", "--set", "platform.mcpInjectToolPrefixes=postgres\\,sandbox")
    assert [c["name"] for c in spec["initContainers"]] == ["migrate"]
    assert spec["initContainers"][0]["args"] == ["zelkor_sidecar.migrate"]
    assert [c["name"] for c in spec["containers"]] == ["sidecar", "agent"]

    sidecar, agent = _c(spec, "sidecar"), _c(spec, "agent")
    assert sidecar["image"].startswith("ghcr.io/devopssquaddev/zelkor-sidecar:2.4.0")
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
