"""S-18 (P3) L3: every running agent's OPENAI_BASE_URL is the in-cluster `{release}-ai-gateway`
Service (or, for a sidecar runtime, the sidecar on loopback). Never the Envoy data-plane FQDN, a
public host, or a provider URL, which would skip the consumer key and NeMo."""
from __future__ import annotations

import json
import os
from urllib.parse import urlparse

import pytest

from tests.helpers.kube import kubectl_run

RELEASE = os.environ.get("ZELKOR_PLATFORM_RELEASE", "zelkor-platform")


def _ok(url: str) -> bool:
    u = urlparse(url)
    host = u.hostname or ""
    if host == "127.0.0.1" and u.port == 8001:  # sidecar runtime: the sidecar forwards to the gateway
        return True
    svc = f"{RELEASE}-ai-gateway"
    return host == svc or (host.startswith(f"{svc}.") and host.endswith(".svc.cluster.local"))


def test_s18_agents_call_the_in_cluster_ai_gateway():
    if not os.environ.get("KUBECONTEXT"):
        pytest.skip("KUBECONTEXT not set")
    r = kubectl_run(["get", "deploy", "-A", "-o", "json"], namespace="")
    assert r.returncode == 0, r.stderr
    seen, bad = [], []
    for d in json.loads(r.stdout)["items"]:
        labels = d["metadata"].get("labels") or {}
        if labels.get("zelkor.io/workload-type") != "agent" and d["metadata"]["name"] != f"{RELEASE}-aegra":
            continue
        for c in d["spec"]["template"]["spec"].get("containers", []):
            for e in c.get("env") or []:
                if e["name"] == "OPENAI_BASE_URL" and e.get("value"):
                    where = f"{d['metadata']['namespace']}/{d['metadata']['name']}/{c['name']}"
                    seen.append(where)
                    if not _ok(e["value"]):
                        bad.append(f"{where}: {e['value']}")
    if not seen:
        pytest.skip("no agent sets OPENAI_BASE_URL")
    assert not bad, "\n".join(bad)
