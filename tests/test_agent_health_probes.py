"""Kubernetes health probes on Aegra agent Deployments (helm template, no cluster)."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
PLATFORM_CHART = ROOT / "charts" / "zelkor-platform"
AGENT_CHART = ROOT / "charts" / "zelkor-agent"
FINSERVE_CHART = ROOT / "examples" / "finserve" / "chart"

SECRET_SETS = [
    "postgresql.auth.password=test-pg",
    "clickhouse.auth.password=test-ch",
    "seaweedfs.auth.accessKey=test-ak",
    "seaweedfs.auth.secretKey=test-sk",
    "langfuse.nextauthSecret=test-na",
    "langfuse.salt=test-salt-1234567890",
    "langfuse.encryptionKey=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    "langfuse.nextauthUrl=https://langfuse.example.com",
]

AGENT_SETS = [
    "graphId=demo-graph",
    "platform.databaseUrl=postgres://zelkor:x@pg:5432/aegra",
    "platform.valkeyUrl=redis://vk:6379/0",
]

FINSERVE_PLATFORM_SETS = [
    "desk.platform.databaseUrl=postgres://zelkor:x@pg:5432/aegra",
    "desk.platform.valkeyUrl=redis://vk:6379/0",
    "quant.platform.databaseUrl=postgres://zelkor:x@pg:5432/aegra",
    "quant.platform.valkeyUrl=redis://vk:6379/0",
    "coder.platform.databaseUrl=postgres://zelkor:x@pg:5432/aegra",
    "coder.platform.valkeyUrl=redis://vk:6379/0",
]

EXPECTED = {
    "startupProbe": ("/health", 8000),
    "livenessProbe": ("/live", 8000),
    "readinessProbe": ("/ready", 8000),
}


def _helm_platform(*extra: str) -> subprocess.CompletedProcess[str]:
    cmd = ["helm", "template", "zelkor-platform", str(PLATFORM_CHART), "--namespace", "zelkor"]
    for item in SECRET_SETS:
        cmd.extend(["--set", item])
    cmd.extend(extra)
    return subprocess.run(cmd, check=False, capture_output=True, text=True)


def _helm_agent(*extra: str) -> subprocess.CompletedProcess[str]:
    cmd = ["helm", "template", "demo-agent", str(AGENT_CHART), "--namespace", "zelkor"]
    for item in AGENT_SETS:
        cmd.extend(["--set", item])
    cmd.extend(extra)
    return subprocess.run(cmd, check=False, capture_output=True, text=True)


def _docs(rendered: str) -> list[dict]:
    return [d for d in yaml.safe_load_all(rendered) if d]


def _named(docs: list[dict], kind: str, name: str) -> dict:
    matches = [d for d in docs if d.get("kind") == kind and d["metadata"]["name"] == name]
    assert matches, f"missing {kind}/{name}"
    return matches[0]


def _container(deploy: dict, name: str) -> dict:
    containers = deploy["spec"]["template"]["spec"]["containers"]
    matches = [c for c in containers if c["name"] == name]
    assert matches, f"missing container {name!r} in {deploy['metadata']['name']}"
    return matches[0]


def _assert_aegra_probes(container: dict) -> None:
    for probe_key, (path, port) in EXPECTED.items():
        assert probe_key in container, f"missing {probe_key}"
        http = container[probe_key]["httpGet"]
        assert http["path"] == path, probe_key
        assert http["port"] == port, probe_key


def test_platform_aegra_deployment_has_standard_probes():
    proc = _helm_platform()
    assert proc.returncode == 0, proc.stderr
    deploy = _named(_docs(proc.stdout), "Deployment", "zelkor-platform-aegra")
    _assert_aegra_probes(_container(deploy, "aegra"))


def test_zelkor_agent_deployment_has_standard_probes():
    proc = _helm_agent()
    assert proc.returncode == 0, proc.stderr
    deploy = _docs(proc.stdout)[1]
    assert deploy["kind"] == "Deployment"
    _assert_aegra_probes(_container(deploy, "agent"))


def test_zelkor_agent_null_startup_omits_startup_only():
    proc = _helm_agent("--set", "startupProbe=null")
    assert proc.returncode == 0, proc.stderr
    deploy = _docs(proc.stdout)[1]
    container = _container(deploy, "agent")
    assert "startupProbe" not in container
    assert container["livenessProbe"]["httpGet"]["path"] == "/live"
    assert container["readinessProbe"]["httpGet"]["path"] == "/ready"


@pytest.fixture(scope="module")
def finserve_rendered() -> str:
    build = subprocess.run(
        ["helm", "dependency", "build", str(FINSERVE_CHART)],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(FINSERVE_CHART),
    )
    assert build.returncode == 0, build.stderr
    cmd = [
        "helm",
        "template",
        "finserve",
        str(FINSERVE_CHART),
        "--namespace",
        "zelkor",
        "-f",
        str(FINSERVE_CHART / "values.yaml"),
    ]
    for item in FINSERVE_PLATFORM_SETS:
        cmd.extend(["--set", item])
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def test_finserve_workers_have_standard_probes(finserve_rendered: str):
    docs = _docs(finserve_rendered)
    for name in ("finserve-desk", "finserve-quant", "finserve-coder"):
        deploy = _named(docs, "Deployment", name)
        _assert_aegra_probes(_container(deploy, "agent"))
