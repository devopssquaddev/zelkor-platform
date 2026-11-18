"""CE-21 render contract: agent pods without DNS (agent chart side)."""
from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "charts" / "zelkor-agent"
MAP_API = "admissionregistration.k8s.io/v1/MutatingAdmissionPolicy"
BASE = ["--set", "graphId=g", "--set", "image.repository=ghcr.io/acme/agent", "--set-string", "image.tag=1.0.0",
        "--set", "platform.releaseName=zelkor-platform", "--set", "security.networkPolicies.enabled=true"]
ALIASES = ["--set", "platform.hostAliases[0].ip=10.43.175.236",
           "--set", "platform.hostAliases[0].hostnames[0]=zelkor-platform-ai-gateway",
           "--set", "platform.hostAliases[0].hostnames[1]=zelkor-platform-mcp"]


def _docs(*extra: str) -> list[dict]:
    proc = subprocess.run(["helm", "template", "a", str(CHART), *BASE, *extra],
                          check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return [d for d in yaml.safe_load_all(proc.stdout) if d]


def _pod(docs: list[dict]) -> dict:
    return next(d for d in docs if d["kind"] == "Deployment")["spec"]["template"]


def _egress_allows_dns(docs: list[dict]) -> bool:
    np = next(d for d in docs if d["kind"] == "NetworkPolicy" and d["metadata"]["name"].endswith("-egress"))
    return any(p.get("port") == 53 for r in np["spec"]["egress"] for p in r.get("ports", []))


def test_host_aliases_from_zelkor_deploy_lock_the_pod():
    docs = _docs(*ALIASES)
    pod = _pod(docs)
    assert pod["spec"]["dnsPolicy"] == "None"
    assert pod["spec"]["dnsConfig"] == {"nameservers": ["127.0.0.1"]}
    assert pod["spec"]["hostAliases"] == [{"ip": "10.43.175.236",
                                           "hostnames": ["zelkor-platform-ai-gateway", "zelkor-platform-mcp"]}]
    assert pod["metadata"]["labels"]["zelkor.io/dns-lockdown"] == "on"
    assert pod["metadata"]["labels"]["zelkor.io/platform-release"] == "zelkor-platform"
    assert not _egress_allows_dns(docs)


def test_admission_policy_cluster_locks_without_host_aliases():
    docs = _docs("--api-versions", MAP_API)
    pod = _pod(docs)
    assert pod["spec"]["dnsPolicy"] == "None" and "hostAliases" not in pod["spec"]
    assert pod["metadata"]["labels"]["zelkor.io/dns-lockdown"] == "on"
    assert not _egress_allows_dns(docs)


def test_plain_helm_on_an_older_cluster_keeps_dns_and_is_marked():
    docs = _docs()
    pod = _pod(docs)
    assert "dnsPolicy" not in pod["spec"]
    assert "zelkor.io/dns-lockdown" not in pod["metadata"]["labels"]
    assert pod["metadata"]["annotations"]["zelkor.io/dns-lockdown"] == "inactive"
    assert _egress_allows_dns(docs)


def test_lockdown_off_keeps_dns_unmarked():
    docs = _docs("--set", "security.dnsLockdown.enabled=false", *ALIASES)
    pod = _pod(docs)
    assert "dnsPolicy" not in pod["spec"] and "hostAliases" not in pod["spec"]
    assert "zelkor.io/dns-lockdown" not in (pod["metadata"].get("annotations") or {})
    assert _egress_allows_dns(docs)
