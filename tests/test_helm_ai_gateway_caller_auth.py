"""AI Gateway caller auth (2.4.1): no /v1 without a key; only NeMo's key reaches providers.

Before this, any in-cluster pod could skip NeMo by sending x-zelkor-guardrails-bypass: 1 and an
x-ai-eg-model header, with no key at all. Now the agent route has no provider rules and needs the
consumer key; providers sit on a NeMo-only hostname behind a key only NeMo pods receive.
"""
from __future__ import annotations

import base64

import yaml

from tests.test_agent_health_probes import _helm_agent
from tests.test_helm_ai_gateway_providers import _docs, _helm, _kinds, _named, _nemo_config_models

OLLAMA = ("--set", "workspace.models.providers.ollamaCloud.apiKey=ollama-key")
BYPASS = "x-zelkor-guardrails-bypass"
CONSUMER = "zelkor-platform-ai-gateway-consumer"
NEMO = "zelkor-platform-ai-gateway-nemo"


def _render(*extra):
    return _docs(_helm(*OLLAMA, *extra))


def _secret_value(docs, name, key):
    return base64.b64decode(_named(docs, "Secret", name)["data"][key]).decode()


def _pods(docs):
    for d in docs:
        if d.get("kind") in ("Deployment", "StatefulSet", "Job"):
            yield d["metadata"]["name"], d["spec"]["template"]["spec"]


def _env_refs(spec):
    """(container, env name, value or ('secret', name, key))."""
    for c in (spec.get("initContainers") or []) + spec.get("containers", []):
        for e in c.get("env") or []:
            ref = ((e.get("valueFrom") or {}).get("secretKeyRef") or {})
            yield c["name"], e["name"], (("secret", ref["name"], ref["key"]) if ref else e.get("value"))


def test_keys_exist_and_explicit_consumer_key_is_used_verbatim():
    docs = _render()
    assert len(_secret_value(docs, CONSUMER, "agents")) >= 32
    assert len(_secret_value(docs, NEMO, "nemo")) >= 32
    assert _secret_value(docs, CONSUMER, "agents") != _secret_value(docs, NEMO, "nemo")
    assert _secret_value(_render("--set", "workspace.models.consumerKey=ck-given"), CONSUMER, "agents") == "ck-given"


def test_security_policies_bind_each_route_to_its_key():
    docs = _render()
    agent = _named(docs, "SecurityPolicy", "zelkor-platform-aigateway-caller-auth")["spec"]
    nemo = _named(docs, "SecurityPolicy", "zelkor-platform-aigateway-nemo-auth")["spec"]
    assert [r["name"] for r in agent["targetRefs"]] == ["zelkor-platform-aigateway-route"]
    assert sorted(r["name"] for r in nemo["targetRefs"]) == ["zelkor-platform-aigateway-nemo-route",
                                                             "zelkor-platform-unknown-model"]
    for spec, secret in ((agent, CONSUMER), (nemo, NEMO)):
        auth = spec["apiKeyAuth"]
        assert auth["credentialRefs"] == [{"name": secret}]
        assert auth["extractFrom"] == [{"headers": ["authorization"]}]
        assert auth["sanitize"] is True


def test_agent_route_has_no_provider_rules():
    route = _named(_render(), "AIGatewayRoute", "zelkor-platform-aigateway-route")
    for rule in route["spec"]["rules"]:
        headers = [h["name"] for m in rule.get("matches") or [] for h in m.get("headers") or []]
        assert BYPASS not in headers
        assert [b["name"] for b in rule["backendRefs"]] == ["zelkor-platform-backend-nemo"]


def test_provider_route_and_reject_live_on_nemo_hostnames_only():
    docs = _render()
    agent_hosts = set(_named(docs, "AIGatewayRoute", "zelkor-platform-aigateway-route")["spec"]["hostnames"])
    nemo_route = _named(docs, "AIGatewayRoute", "zelkor-platform-aigateway-nemo-route")
    nemo_hosts = set(nemo_route["spec"]["hostnames"])
    assert nemo_hosts == {NEMO, f"{NEMO}.zelkor.svc.cluster.local"}
    assert not agent_hosts & nemo_hosts
    assert set(_named(docs, "HTTPRoute", "zelkor-platform-unknown-model")["spec"]["hostnames"]) == nemo_hosts
    assert {b["name"] for r in nemo_route["spec"]["rules"] for b in r["backendRefs"]} == {"zelkor-platform-backend-ollama-cloud"}


def test_only_nemo_holds_the_nemo_key_and_no_pod_has_a_literal_key():
    docs = _render("--set", "workspace.models.consumerKey=ck-given")
    nemo_users = set()
    for name, spec in _pods(docs):
        for _c, env, val in _env_refs(spec):
            if isinstance(val, tuple) and val[1] == NEMO:
                nemo_users.add(name)
            assert val != "ck-given", f"{name}/{env} carries the consumer key as a literal"
    assert nemo_users == {"zelkor-platform-nemo"}
    nemo = dict((env, val) for _c, env, val in _env_refs(dict(_pods(docs))["zelkor-platform-nemo"]))
    assert nemo["OPENAI_API_KEY"] == ("secret", NEMO, "nemo")
    assert nemo["MAIN_MODEL_BASE_URL"] == f"http://{NEMO}:80/v1"
    aegra = dict((env, val) for _c, env, val in _env_refs(dict(_pods(docs))["zelkor-platform-aegra"]))
    assert aegra["OPENAI_API_KEY"] == ("secret", CONSUMER, "agents")


def test_nemo_config_calls_the_nemo_route():
    for row in _nemo_config_models(_render("--set", "workspace.policies.nemo.selfCheck.enabled=true")):
        params = row["parameters"]
        assert params["base_url"] == f"http://{NEMO}:80/v1"
        assert "Host" not in params["default_headers"]


def test_nemo_reachable_only_from_envoy():
    docs = _render("--set", "security.networkPolicies.enabled=true", "--set", "security.mcp.acceptUnprotectedBackends=false")
    for name in ("zelkor-platform-agent-egress", "zelkor-platform-aegra-egress"):
        egress = _named(docs, "NetworkPolicy", name)["spec"]["egress"]
        assert not any(
            (peer.get("podSelector") or {}).get("matchLabels", {}).get("app.kubernetes.io/component") == "guardrails"
            for rule in egress for peer in rule.get("to") or []), name
    ingress = _named(docs, "NetworkPolicy", "zelkor-platform-guardrails-dest-deny")["spec"]["ingress"]
    peers = [p for rule in ingress for p in rule.get("from") or []]
    assert peers == [{"namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": "envoy-gateway-system"}}}]


def _agent_env(*extra):
    r = _helm_agent(*extra)
    assert r.returncode == 0, r.stderr
    (d,) = [x for x in yaml.safe_load_all(r.stdout) if x and x.get("kind") == "Deployment"]
    out = {}
    for c in d["spec"]["template"]["spec"]["containers"]:
        for e in c.get("env") or []:
            ref = (e.get("valueFrom") or {}).get("secretKeyRef")
            out[(c["name"], e["name"])] = (ref["name"], ref["key"]) if ref else e.get("value")
    return out


def test_agent_chart_inherits_the_consumer_key_from_the_platform_release():
    env = _agent_env("--set", "platform.consumerKey=", "--set", "platform.releaseName=zelkor-platform")
    assert env[("aegra", "OPENAI_API_KEY")] == (CONSUMER, "agents") if ("aegra", "OPENAI_API_KEY") in env else True
    assert any(v == (CONSUMER, "agents") for k, v in env.items() if k[1] == "OPENAI_API_KEY")
    side = _agent_env("--set", "runtime=a2a", "--set", "platform.consumerKey=", "--set", "platform.releaseName=zelkor-platform")
    assert side[("sidecar", "ZELKOR_CONSUMER_KEY")] == (CONSUMER, "agents")
    assert side[("agent", "OPENAI_API_KEY")] == "via-sidecar"
    explicit = _agent_env("--set", "platform.consumerKey=ck-x", "--set", "platform.releaseName=zelkor-platform")
    assert any(v == "ck-x" for k, v in explicit.items() if k[1] == "OPENAI_API_KEY")


def _annotations(docs, name):
    return _named(docs, "Deployment", name)["spec"]["template"]["metadata"].get("annotations") or {}


def _bootstrap_job(docs):
    (job,) = [d for d in docs if d.get("kind") == "Job" and d["metadata"]["name"].startswith("zelkor-platform-langfuse-bootstrap-")]
    return job["metadata"]["name"]


def test_rotating_the_consumer_key_restarts_its_users_and_reruns_the_seed():
    one, same, two = (_render("--set", f"workspace.models.consumerKey={k}") for k in ("ck-1", "ck-1", "ck-2"))
    for name in ("zelkor-platform-aegra", "zelkor-platform-mcp-aigateway", "zelkor-platform-mcp-qdrant"):
        a1, a1b, a2 = (_annotations(d, name).get("checksum/ai-gateway-agents") for d in (one, same, two))
        assert a1 and a1 == a1b != a2, name
    assert "checksum/ai-gateway-nemo" in _annotations(one, "zelkor-platform-nemo")
    # The seed stores the key in the Langfuse LLM connection: a new key means a new Job (re-run).
    assert _bootstrap_job(one) == _bootstrap_job(same) != _bootstrap_job(two)


def test_agent_pods_track_the_key_they_use():
    def checksum(*extra):
        r = _helm_agent(*extra)
        assert r.returncode == 0, r.stderr
        (d,) = [x for x in yaml.safe_load_all(r.stdout) if x and x.get("kind") == "Deployment"]
        return d["spec"]["template"]["metadata"]["annotations"]["checksum/ai-gateway-consumer"]
    assert checksum("--set", "platform.consumerKey=ck-1") == checksum("--set", "platform.consumerKey=ck-1")
    assert checksum("--set", "platform.consumerKey=ck-1") != checksum("--set", "platform.consumerKey=ck-2")


def test_any_seed_input_renames_the_bootstrap_job():
    """The Job spec is immutable: a changed input must rename the Job, or `helm upgrade` fails while
    the finished Job still exists (TTL). Adding an extra MCP backend used to keep the name."""
    # Seed on; offline renders generate a key unless one is set.
    key = ("--set", "workspace.models.consumerKey=ck-1", "--set", "platform.telemetry.langfuse.init.enabled=true",
           "--set", "platform.telemetry.langfuse.init.orgId=o", "--set", "platform.telemetry.langfuse.init.orgName=o", "--set", "platform.telemetry.langfuse.init.projectId=p",
           "--set", "platform.telemetry.langfuse.init.projectName=p", "--set", "platform.telemetry.langfuse.surfaces.llmConnection.enabled=true")
    base = _render(*key)
    extra = _render(*key, "--set", "workspace.tools.extraBackends[0].name=saas",
                    "--set", "workspace.tools.extraBackends[0].fqdn.hostname=mcp.example.com",
                    "--set", "workspace.tools.extraBackends[0].fqdn.port=443")
    assert _bootstrap_job(base) != _bootstrap_job(extra)
    assert _bootstrap_job(base) == _bootstrap_job(_render(*key))  # stable when nothing changed


def test_bootstrap_job_takes_credentials_by_reference():
    """Literal env values show up in `kubectl get job` and in Helm upgrade errors."""
    docs = _render("--set", "platform.telemetry.langfuse.init.enabled=true",
                   "--set", "platform.telemetry.langfuse.init.orgId=o", "--set", "platform.telemetry.langfuse.init.orgName=o",
                   "--set", "platform.telemetry.langfuse.init.projectId=p", "--set", "platform.telemetry.langfuse.init.projectName=p",
                   "--set", "platform.telemetry.langfuse.init.projectPublicKey=pk-lf-inline",
                   "--set", "platform.telemetry.langfuse.init.projectSecretKey=sk-lf-inline",
                   "--set", "platform.telemetry.langfuse.surfaces.llmConnection.enabled=true")
    (job,) = [d for d in docs if d.get("kind") == "Job" and d["metadata"]["name"].startswith("zelkor-platform-langfuse-bootstrap-")]
    env = {e["name"]: e for e in job["spec"]["template"]["spec"]["containers"][0]["env"]}
    for name in ("DATABASE_URL", "VALKEY_PASSWORD", "LANGFUSE_SALT", "MCP_AUTH_TOKEN", "LANGFUSE_PUBLIC_KEY",
                 "LANGFUSE_SECRET_KEY", "AI_GATEWAY_CONSUMER_KEY"):
        assert "value" not in env[name] and env[name]["valueFrom"]["secretKeyRef"], name
    dumped = yaml.safe_dump(job)
    assert "test-pg" not in dumped and "test-salt" not in dumped and "sk-lf-inline" not in dumped
    secret = _named(docs, "Secret", "zelkor-platform-langfuse-bootstrap")
    assert set(secret["stringData"]) == {"database-url", "valkey-password", "mcp-auth-token"}
