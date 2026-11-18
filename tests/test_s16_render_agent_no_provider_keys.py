"""S-16 (P13) L2: no agent-side workload is handed a provider API key, the NeMo provider key or the
tenant JWT signing key: not by env, envFrom, or a mounted Secret. Agent side = Aegra, the sandbox
workers, and an agent release of charts/zelkor-agent. The live env dump is test_s16_agent_env_no_secrets.py."""
from __future__ import annotations

import pytest
import yaml

from tests.test_agent_health_probes import _helm_agent
from tests.test_helm_ai_gateway_providers import _docs, _helm, _kinds

PROVIDERS = ["--set", "workspace.models.providers.openai.apiKey=sk-test",
             "--set", "workspace.models.providers.anthropic.apiKey=ant-test",
             "--set", "workspace.models.providers.ollamaCloud.apiKey=ollama-test"]
NEMO_KEY = "zelkor-platform-ai-gateway-nemo"
SIGNING = "zelkor-platform-tenant-jwt-signing"


def _secret_refs(spec: dict) -> set[str]:
    out = set()
    for c in (spec.get("initContainers") or []) + spec.get("containers", []):
        for e in c.get("env") or []:
            if ref := (e.get("valueFrom") or {}).get("secretKeyRef"):
                out.add(ref["name"])
        for src in c.get("envFrom") or []:
            if ref := src.get("secretRef"):
                out.add(ref["name"])
    for v in spec.get("volumes") or []:
        if v.get("secret"):
            out.add(v["secret"]["secretName"])
        for s in (v.get("projected") or {}).get("sources") or []:
            if s.get("secret"):
                out.add(s["secret"]["name"])
    return out


def _literal_keys(spec: dict) -> list[str]:
    return [f"{c['name']}/{e['name']}" for c in spec.get("containers", []) for e in c.get("env") or []
            if e.get("value") and e["name"].endswith(("_API_KEY", "_SECRET_KEY")) and e["value"] not in ("via-sidecar",)
            and not e["name"].startswith("LANGFUSE_")]


@pytest.fixture(scope="module")
def platform_docs():
    return _docs(_helm(*PROVIDERS))


def _provider_secrets(docs) -> set[str]:
    names = {p["spec"]["apiKey"]["secretRef"]["name"] for p in _kinds(docs, "BackendSecurityPolicy")
             if (p.get("spec") or {}).get("apiKey")}
    assert names, "fixture renders no provider key: the test would be vacuous"
    return names | {NEMO_KEY, SIGNING}


def _agent_side(docs):
    for d in _kinds(docs, "Deployment"):
        name = d["metadata"]["name"]
        if name == "zelkor-platform-aegra" or "sandbox-worker" in name:
            yield name, d["spec"]["template"]["spec"]


def test_s16_platform_agent_side_pods_get_no_provider_or_signing_key(platform_docs):
    forbidden = _provider_secrets(platform_docs)
    seen = []
    for name, spec in _agent_side(platform_docs):
        seen.append(name)
        assert not _secret_refs(spec) & forbidden, f"{name} mounts {sorted(_secret_refs(spec) & forbidden)}"
        assert not _literal_keys(spec), f"{name} has literal keys {_literal_keys(spec)}"
    assert "zelkor-platform-aegra" in seen and any("sandbox-worker" in n for n in seen), seen


@pytest.mark.parametrize("runtime", [[], ["--set", "runtime=a2a"]], ids=["aegra-worker", "sidecar-runtime"])
def test_s16_agent_release_gets_no_provider_or_signing_key(platform_docs, runtime):
    r = _helm_agent("--set", "platform.releaseName=zelkor-platform", *runtime)
    assert r.returncode == 0, r.stderr
    (dep,) = [d for d in yaml.safe_load_all(r.stdout) if d and d.get("kind") == "Deployment"]
    spec = dep["spec"]["template"]["spec"]
    assert not _secret_refs(spec) & _provider_secrets(platform_docs)
    assert not _literal_keys(spec), _literal_keys(spec)
