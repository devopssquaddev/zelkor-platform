"""AI Gateway caller auth on a live install (UAT-01/18/23/28, S-83). Skips without its env.

KUBECONTEXT for in-cluster checks; AI_GATEWAY_PUBLIC_URL for the north-south host;
ZELKOR_AGENT_NAMESPACE for an agent release outside the platform namespace.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess

import httpx
import pytest

from tests.helpers.kube import kubectl_cmd, kubectl_run
from tests.helpers.langfuse import langfuse_get
from tests.helpers.runtime_agents import require_kube

REL = os.environ.get("ZELKOR_PLATFORM_RELEASE", "zelkor-platform")
NS = os.environ.get("ZELKOR_PLATFORM_NAMESPACE", "zelkor")
KEY_USERS = {"aegra": "agents", "mcp-aigateway": "agents", "mcp-qdrant": "agents", "nemo": "nemo"}


def _secret(name: str, key: str, namespace: str | None = None) -> str:
    proc = kubectl_run(["get", "secret", name, "-o", f"jsonpath={{.data.{key}}}"], namespace=namespace)
    if proc.returncode != 0 or not proc.stdout.strip():
        pytest.skip(f"secret {name}/{key} not found (pre-2.4.1 install?)")
    return base64.b64decode(proc.stdout.strip()).decode()


def test_key_users_run_the_current_key():
    """A rotation that did not restart a reader shows up as a stale checksum (that reader would 401)."""
    require_kube()
    keys = {"agents": _secret(f"{REL}-ai-gateway-consumer", "agents"), "nemo": _secret(f"{REL}-ai-gateway-nemo", "nemo")}
    for comp, key in KEY_USERS.items():
        proc = kubectl_run(["get", f"deploy/{REL}-{comp}", "-o", "json"])
        if proc.returncode != 0:
            continue  # component disabled
        dep = json.loads(proc.stdout)
        ann = (dep["spec"]["template"]["metadata"].get("annotations") or {}).get(f"checksum/ai-gateway-{key}")
        assert ann == hashlib.sha256(keys[key].encode()).hexdigest()[:16], f"{comp} pods were not rolled onto the current {key} key"
        status = dep.get("status") or {}
        assert status.get("updatedReplicas") == status.get("replicas"), f"{comp} rollout not finished"


def test_public_gateway_host_refuses_requests_without_a_key():
    url = os.environ.get("AI_GATEWAY_PUBLIC_URL", "").rstrip("/")
    if not url:
        pytest.skip("AI_GATEWAY_PUBLIC_URL not set (AI Gateway not published north-south)")
    body = {"model": os.environ.get("DEFAULT_LLM_MODEL", "gpt-oss:20b"), "messages": [{"role": "user", "content": "ok"}]}
    assert httpx.post(f"{url}/v1/chat/completions", json=body, timeout=60).status_code == 401
    bypass = {"x-zelkor-guardrails-bypass": "1", "x-ai-eg-model": body["model"]}
    assert httpx.post(f"{url}/v1/chat/completions", json=body, headers=bypass, timeout=60).status_code == 401


def test_aegra_cannot_reach_nemo_directly():
    require_kube()
    probe = ("import socket\ntry:\n    socket.create_connection((%r, 8000), timeout=4).close(); print('open')\n"
             "except Exception as e:\n    print(type(e).__name__)\n") % f"{REL}-nemo"
    proc = subprocess.run(kubectl_cmd("exec", "-i", f"deploy/{REL}-aegra", "-c", "aegra", "--", "python", "-"),
                          input=probe, capture_output=True, text=True, timeout=60, check=False)
    assert proc.returncode == 0, proc.stderr[-300:]
    assert proc.stdout.strip().splitlines()[-1] != "open", "Aegra reached NeMo without the AI Gateway"


def test_agent_namespace_has_the_consumer_secret():
    ns = os.environ.get("ZELKOR_AGENT_NAMESPACE", "").strip()
    if not ns:
        pytest.skip("ZELKOR_AGENT_NAMESPACE not set")
    require_kube()
    assert _secret(f"{REL}-ai-gateway-consumer", "agents", namespace=ns) == _secret(f"{REL}-ai-gateway-consumer", "agents")
    deps = json.loads(kubectl_run(["get", "deploy", "-l", "zelkor.io/workload-type=agent", "-o", "json"], namespace=ns).stdout)
    refs = [e for d in deps["items"] for c in d["spec"]["template"]["spec"]["containers"] for e in c.get("env") or []
            if e["name"] in ("OPENAI_API_KEY", "ZELKOR_CONSUMER_KEY")]
    assert refs and all(((e.get("valueFrom") or {}).get("secretKeyRef") or {}).get("name") == f"{REL}-ai-gateway-consumer"
                        or e.get("value") == "via-sidecar" for e in refs)


def test_langfuse_llm_connection_points_at_the_gateway():
    try:
        resp = langfuse_get("/api/public/llm-connections")
    except httpx.HTTPError as exc:
        pytest.skip(f"Langfuse not reachable: {exc}")
    assert resp.status_code == 200, resp.text[:200]
    body = resp.json()
    data = body.get("data") if isinstance(body, dict) else body
    conns = [c for c in data or [] if "ai-gateway" in str(c.get("baseURL", ""))]
    assert conns, "no Langfuse LLM connection to the AI Gateway (bootstrap seed did not run?)"
