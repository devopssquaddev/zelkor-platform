"""requirements_zelkor_cli.md §4 behaviours that had no test (coverage audit finding 16):
pull secrets and Langfuse/OTEL reach the agent overlay, `dev` prefers the local env, a digest
skips the build, and the rollout wait honours ZELKOR_ROLLOUT_TIMEOUT_SEC."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from tests.test_zelkor_cli import ROOT, _discover_runner
from zelkor.envfile import Env, add_env, resolve_env
from zelkor.main import _wait_agent_rollout, deploy_from_values

PROD = Env(name="prod", kube_context="k3s", namespace="zelkor")
PLATFORM_VALUES = ("gateway:\n  hosts:\n    agents: agents.example.com\n"
                   "global:\n  imagePullSecrets:\n  - name: ghcr-pull\n")
AEGRA_ENV = [{"name": "LANGFUSE_BASE_URL", "value": "http://langfuse.zelkor.svc:3000"},
             {"name": "LANGFUSE_PUBLIC_KEY", "value": "pk-lf-test"},
             {"name": "LANGFUSE_SECRET_KEY", "value": "sk-lf-test"},
             {"name": "OTEL_TARGETS", "value": "langfuse"}]


def _platform_runner(captured: dict):
    base = _discover_runner(captured)

    def runner(argv, **kw):
        res = base(argv, **kw)
        if "helm" in argv and "get" in argv and "values" in argv:
            return SimpleNamespace(returncode=0, stdout=PLATFORM_VALUES, stderr="")
        if "get" in argv and "deploy" in argv and "-l" in argv:
            data = json.loads(res.stdout)
            data["items"][0]["spec"]["template"]["spec"]["containers"][0]["env"] += AEGRA_ENV
            return SimpleNamespace(returncode=0, stdout=json.dumps(data), stderr="")
        return res
    return runner


def _values(tmp_path: Path, image: str) -> Path:
    p = tmp_path / "values.yaml"
    p.write_text(f"graphId: desk\nimage:\n{image}\n", encoding="utf-8")
    return p


def _deploy(tmp_path: Path, image: str, **kw) -> tuple[dict, dict]:
    captured: dict = {}
    result = deploy_from_values(values_path=_values(tmp_path, image), env=PROD,
                                agent_chart=ROOT / "charts" / "zelkor-agent",
                                platform_chart=ROOT / "charts" / "zelkor-platform",
                                runner=_platform_runner(captured), **kw)
    return result, captured


def test_pull_secrets_and_trace_config_reach_the_agent_overlay(tmp_path):
    _, captured = _deploy(tmp_path, "  repository: ghcr.io/acme/desk\n  tag: '1.0.0'")
    overlay = yaml.safe_load(captured["values"])
    assert overlay["global"]["imagePullSecrets"] == [{"name": "ghcr-pull"}]
    platform = overlay["platform"]
    assert platform["langfuseBaseUrl"] == "http://langfuse.zelkor.svc:3000"
    assert platform["langfusePublicKey"] == "pk-lf-test"
    assert platform["langfuseSecretKey"] == "sk-lf-test"
    assert platform["otelTargets"] == "langfuse"


def test_digest_skips_the_build_and_pins_the_image(tmp_path):
    (tmp_path / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    digest = "sha256:" + "a" * 64
    result, captured = _deploy(tmp_path, f"  repository: ghcr.io/acme/desk\n  digest: '{digest}'",
                               skip_build=False)
    assert not any(c and c[0] == "docker" for c in captured["commands"]), "a digest must not rebuild"
    assert result["image"] == f"ghcr.io/acme/desk@{digest}"


def test_dockerfile_without_digest_builds_off_kind_only_with_a_registry(tmp_path, monkeypatch):
    (tmp_path / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    monkeypatch.delenv("ZELKOR_IMAGE_REGISTRY", raising=False)
    with pytest.raises(RuntimeError, match="ZELKOR_IMAGE_REGISTRY"):
        _deploy(tmp_path, "  repository: ghcr.io/acme/desk\n  tag: '1.0.0'", skip_build=False)


def test_dev_prefers_the_local_env_over_current(tmp_path):
    store = tmp_path / "envs.yaml"
    add_env(Env(name="local", kube_context="kind-zelkor", namespace="default"), store_path=store)
    add_env(PROD, store_path=store)  # becomes current
    assert resolve_env(store_path=store, cwd=tmp_path).name == "prod"
    assert resolve_env(prefer_local=True, store_path=store, cwd=tmp_path).name == "local"
    assert resolve_env(name="prod", prefer_local=True, store_path=store, cwd=tmp_path).name == "prod"


def test_rollout_timeout_env_sets_the_wait():
    code = "import zelkor.main as m; print(m.ROLLOUT_WAIT_SEC)"
    env = {**os.environ, "PYTHONPATH": str(ROOT / "cli" / "src"), "ZELKOR_ROLLOUT_TIMEOUT_SEC": "7"}
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True)
    assert float(out.stdout.strip()) == 7.0


def test_rollout_wait_stops_at_the_timeout():
    not_ready = json.dumps({"kind": "Deployment", "metadata": {"generation": 1}, "spec": {"replicas": 1},
                            "status": {"observedGeneration": 1, "availableReplicas": 0}})

    def runner(argv, **_kw):
        if "get" in argv and "deploy" in argv:
            return SimpleNamespace(returncode=0, stdout=not_ready, stderr="")
        return SimpleNamespace(returncode=0, stdout=json.dumps({"items": []}), stderr="")
    with pytest.raises(RuntimeError):
        _wait_agent_rollout(PROD, "desk", runner=runner, timeout_sec=0)
