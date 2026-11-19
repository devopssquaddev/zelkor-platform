"""S-16 (P13) L3: on the running cluster, no agent-side Deployment holds a provider API key, the NeMo
provider key or the tenant JWT signing key: not as a literal, not by env/envFrom Secret reference,
not as a mounted Secret. Agent side = platform Aegra, sandbox workers, every
zelkor.io/workload-type=agent Deployment in any namespace. The provider Secrets come from the
cluster's BackendSecurityPolicies, so the check follows whatever providers this install has."""
from __future__ import annotations

import json
import os
import re

import pytest

from tests.helpers.kube import kubectl_run
from tests.test_s16_render_agent_no_provider_keys import _secret_refs

RELEASE = os.environ.get("ZELKOR_PLATFORM_RELEASE", "zelkor-platform")
KEYLIKE = re.compile(r"^(sk-|sk-ant-|AIza|gsk_|xai-|pk-lf-|sk-lf-)|^eyJ")
LANGFUSE_OK = {"LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"}  # trace export keys, not provider keys


def _get(*args: str) -> list[dict]:
    r = kubectl_run(["get", *args, "-o", "json"], namespace="")
    if r.returncode != 0:
        pytest.skip(r.stderr.strip()[:200])
    return json.loads(r.stdout).get("items") or []


@pytest.fixture(scope="module")
def forbidden() -> set[str]:
    if not os.environ.get("KUBECONTEXT"):
        pytest.skip("KUBECONTEXT not set")
    names = {f"{RELEASE}-ai-gateway-nemo", f"{RELEASE}-tenant-jwt-signing"}
    for p in _get("backendsecuritypolicies.aigateway.envoyproxy.io", "-A"):
        ref = ((p.get("spec") or {}).get("apiKey") or {}).get("secretRef") or {}
        if ref.get("name"):
            names.add(ref["name"])
    return names


def _agent_side() -> list[dict]:
    deps = _get("deploy", "-A")
    out = []
    for d in deps:
        name, labels = d["metadata"]["name"], d["metadata"].get("labels") or {}
        if (labels.get("zelkor.io/workload-type") == "agent" or name == f"{RELEASE}-aegra"
                or "sandbox-worker" in name):
            out.append(d)
    return out


def test_s16_agent_side_deployments_hold_no_provider_or_signing_key(forbidden):
    deps = _agent_side()
    assert any(d["metadata"]["name"] == f"{RELEASE}-aegra" for d in deps) or deps, "no agent-side Deployment found"
    leaks = []
    for d in deps:
        spec = d["spec"]["template"]["spec"]
        where = f"{d['metadata']['namespace']}/{d['metadata']['name']}"
        for ref in sorted(_secret_refs(spec) & forbidden):
            leaks.append(f"{where} references Secret {ref}")
        for c in (spec.get("initContainers") or []) + spec.get("containers", []):
            for e in c.get("env") or []:
                v = e.get("value") or ""
                if v and e["name"] not in LANGFUSE_OK and KEYLIKE.search(v):
                    leaks.append(f"{where}/{c['name']} env {e['name']} holds a key-shaped literal")
    assert not leaks, "\n".join(leaks)
