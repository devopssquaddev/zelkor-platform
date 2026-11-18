"""CE-21 render contract: agent pods without DNS (platform chart side)."""
from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "charts" / "zelkor-platform"
LOCAL = ROOT / "profiles" / "values-local.yaml"
MAP_API = "admissionregistration.k8s.io/v1/MutatingAdmissionPolicy"


def _render(*extra: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    cmd = ["helm", "template", "zelkor-platform", str(CHART), "--namespace", "zelkor",
           "-f", str(LOCAL), "--set", "platform.tenants.jwt.remoteJwksUri=", *extra]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if check:
        assert proc.returncode == 0, proc.stderr
    return proc


def _docs(*extra: str) -> list[dict]:
    return [d for d in yaml.safe_load_all(_render(*extra).stdout) if d]


def _kind(docs: list[dict], kind: str) -> list[dict]:
    return [d for d in docs if d.get("kind") == kind]


def _writer_env(docs: list[dict]) -> dict[str, str]:
    jobs = [j for j in _kind(docs, "Job") if j["metadata"]["name"].startswith("zelkor-platform-agent-hosts-")]
    assert len(jobs) == 1, [j["metadata"]["name"] for j in _kind(docs, "Job")]
    return {e["name"]: e.get("value", "") for e in jobs[0]["spec"]["template"]["spec"]["containers"][0]["env"]}


def _agent_egress(docs: list[dict]) -> dict:
    return next(d for d in _kind(docs, "NetworkPolicy") if d["metadata"]["name"] == "zelkor-platform-agent-egress")


def _allows_dns(policy: dict) -> bool:
    return any(p.get("port") == 53 for rule in policy["spec"].get("egress", []) for p in rule.get("ports", []))


def test_default_writes_the_host_map_and_agent_egress_has_no_dns():
    docs = _docs()
    env = _writer_env(docs)
    services = env["AGENT_HOSTS_SERVICES"].split()
    assert "zelkor-platform-ai-gateway" in services and "zelkor-platform-mcp" in services
    assert env["AGENT_HOSTS_REQUIRED"].split() == ["zelkor-platform-ai-gateway", "zelkor-platform-mcp"]
    assert env["AGENT_HOSTS_CONFIGMAP"] == "zelkor-platform-agent-hosts"
    job = next(j for j in _kind(docs, "Job") if j["metadata"]["name"].startswith("zelkor-platform-agent-hosts-"))
    # A plain Job, never a hook: Helm must not wait on it.
    assert "helm.sh/hook" not in (job["metadata"].get("annotations") or {})
    assert not _allows_dns(_agent_egress(docs))
    # Agents not locked down (older charts, lockdown inactive) keep DNS through their own policy.
    dns = next(d for d in _kind(docs, "NetworkPolicy") if d["metadata"]["name"] == "zelkor-platform-agent-dns-egress")
    assert dns["spec"]["podSelector"]["matchExpressions"] == [
        {"key": "zelkor.io/dns-lockdown", "operator": "NotIn", "values": ["on"]}]
    assert _allows_dns(dns)


def test_no_policy_gives_locked_pods_dns():
    """Every policy allowing port 53 excludes zelkor.io/dns-lockdown=on (S-90 caught aegra-egress)."""
    docs = _docs()
    for np in _kind(docs, "NetworkPolicy"):
        if not _allows_dns(np):
            continue
        sel = np["spec"]["podSelector"]
        labels = sel.get("matchLabels") or {}
        if labels.get("app.kubernetes.io/component") not in ("aegra", None) and "zelkor.io/workload-type" not in labels:
            continue  # selects platform components only (MCP, Langfuse), never agent pods
        assert {"key": "zelkor.io/dns-lockdown", "operator": "NotIn", "values": ["on"]} in \
            (sel.get("matchExpressions") or []), np["metadata"]["name"]


def test_writer_rbac_is_namespaced_and_scoped_to_its_configmap():
    docs = _docs()
    assert not _kind(docs, "ClusterRole") or all(
        "agent-hosts" not in r["metadata"]["name"] for r in _kind(docs, "ClusterRole"))
    roles = [r for r in _kind(docs, "Role") if r["metadata"]["name"] == "zelkor-platform-agent-hosts"]
    assert {r["metadata"]["namespace"] for r in roles} == {"zelkor", "envoy-gateway-system"}
    own = next(r for r in roles if r["metadata"]["namespace"] == "zelkor")
    writes = [rule for rule in own["rules"] if "update" in rule["verbs"]]
    assert writes and all(rule.get("resourceNames") == ["zelkor-platform-agent-hosts"] for rule in writes)


def test_http_api_routes_join_the_host_map():
    docs = _docs("--set", "workspace.tools.httpApis[0].name=github",
                 "--set", "workspace.tools.httpApis[0].url=https://api.github.com",
                 "--set", "workspace.tools.httpApis[0].rules[0].action=Allow")
    assert "zelkor-platform-api-github" in _writer_env(docs)["AGENT_HOSTS_SERVICES"].split()


def test_admission_policy_only_when_the_api_is_served():
    assert not _kind(_docs(), "MutatingAdmissionPolicy")
    docs = _docs("--api-versions", MAP_API)
    (policy,) = _kind(docs, "MutatingAdmissionPolicy")
    (binding,) = _kind(docs, "MutatingAdmissionPolicyBinding")
    selector = policy["spec"]["matchConstraints"]["objectSelector"]
    assert selector["matchLabels"] == {"zelkor.io/platform-release": "zelkor-platform"}
    assert binding["spec"]["paramRef"] == {"name": "zelkor-platform-agent-hosts", "namespace": "zelkor",
                                           "parameterNotFoundAction": "Deny"}
    expr = policy["spec"]["mutations"][0]["jsonPatch"]["expression"]
    # One patch per entry; a CEL-built list of objects panics the 1.36.4 API server.
    assert '"/spec/hostAliases/-"' in expr and "split(" not in expr


def test_lockdown_off_keeps_dns_and_renders_no_writer():
    docs = _docs("--set", "security.dnsLockdown.enabled=false", "--api-versions", MAP_API)
    assert not [j for j in _kind(docs, "Job") if "agent-hosts" in j["metadata"]["name"]]
    assert not _kind(docs, "MutatingAdmissionPolicy")
    assert _allows_dns(_agent_egress(docs))


def test_reuse_values_upgrade_without_the_key_still_locks_down():
    """`helm upgrade --reuse-values` from a pre-CE-21 release carries no security.dnsLockdown."""
    docs = _docs("--set", "security.dnsLockdown=null")
    assert _writer_env(docs)["AGENT_HOSTS_DEADLINE_S"] == "900"
    assert not _allows_dns(_agent_egress(docs))
