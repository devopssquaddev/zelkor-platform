"""Helm render of security.sandbox gVisor provisioning (no cluster)."""
from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "charts" / "zelkor-platform"

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


def _helm(*extra: str) -> subprocess.CompletedProcess[str]:
    cmd = [
        "helm",
        "template",
        "zelkor-platform",
        str(CHART),
        "--namespace",
        "zelkor",
    ]
    for item in SECRET_SETS:
        cmd.extend(["--set", item])
    cmd.extend(extra)
    return subprocess.run(cmd, check=False, capture_output=True, text=True)


def _docs(rendered: str) -> list[dict]:
    return [d for d in yaml.safe_load_all(rendered) if d]


def _kinds(docs: list[dict], kind: str) -> list[dict]:
    return [d for d in docs if d.get("kind") == kind]


def _names(docs: list[dict], kind: str) -> set[str]:
    return {d["metadata"]["name"] for d in _kinds(docs, kind)}


def _gvisor_ds(docs: list[dict]) -> dict | None:
    for ds in _kinds(docs, "DaemonSet"):
        if ds["metadata"].get("namespace") == "kube-system" and "gvisor-installer" in ds["metadata"]["name"]:
            return ds
    return None


def _gvisor_rc(docs: list[dict]) -> dict | None:
    for rc in _kinds(docs, "RuntimeClass"):
        if rc["metadata"]["name"] == "gvisor":
            return rc
    return None


def test_defaults_renders_installer_runtimeclass_and_verify():
    proc = _helm()
    assert proc.returncode == 0, proc.stderr
    docs = _docs(proc.stdout)
    ds = _gvisor_ds(docs)
    assert ds is not None
    spec = ds["spec"]["template"]["spec"]
    assert spec.get("nodeSelector") in (None, {})
    assert "zelkor-platform-gvisor-installer" in ds["metadata"]["name"]
    rc = _gvisor_rc(docs)
    assert rc is not None
    assert rc["handler"] == "runsc"
    assert rc.get("scheduling") is None
    assert "zelkor-platform-gvisor-verify" in _names(docs, "Job")
    verify = next(d for d in _kinds(docs, "Job") if d["metadata"]["name"] == "zelkor-platform-gvisor-verify")
    assert verify["spec"]["template"]["spec"]["runtimeClassName"] == "gvisor"
    verify_ann = (verify.get("metadata") or {}).get("annotations") or {}
    assert "helm.sh/hook" not in verify_ann


def test_gvisor_installer_selector_matches_pod_labels():
    proc = _helm()
    assert proc.returncode == 0, proc.stderr
    ds = _gvisor_ds(_docs(proc.stdout))
    assert ds is not None
    match = ds["spec"]["selector"]["matchLabels"]
    pod_labels = ds["spec"]["template"]["metadata"]["labels"]
    for key, value in match.items():
        assert pod_labels.get(key) == value, f"{key}={value!r} not on pod {pod_labels}"


def test_create_runtimeclass_false_omits_runtimeclass():
    proc = _helm(
        "--set",
        "security.sandbox.provisioning.mode=daemonset",
        "--set",
        "security.sandbox.createRuntimeClass=false",
    )
    assert proc.returncode == 0, proc.stderr
    docs = _docs(proc.stdout)
    assert _gvisor_rc(docs) is None
    assert _gvisor_ds(docs) is not None


def test_preinstalled_without_runtimeclass_renders_nothing():
    proc = _helm(
        "--set",
        "security.sandbox.provisioning.mode=preinstalled",
        "--set",
        "security.sandbox.createRuntimeClass=false",
    )
    assert proc.returncode == 0, proc.stderr
    docs = _docs(proc.stdout)
    assert _gvisor_ds(docs) is None
    assert _gvisor_rc(docs) is None
    assert "zelkor-platform-gvisor-verify" not in _names(docs, "Job")


def test_mode_none_renders_no_gvisor_resources():
    proc = _helm("--set", "security.sandbox.provisioning.mode=none")
    assert proc.returncode == 0, proc.stderr
    docs = _docs(proc.stdout)
    assert _gvisor_ds(docs) is None
    assert _gvisor_rc(docs) is None
    assert "zelkor-platform-gvisor-verify" not in _names(docs, "Job")


def test_sandbox_execution_log_env_on_mcp_and_worker():
    proc = _helm()
    assert proc.returncode == 0, proc.stderr
    docs = _docs(proc.stdout)
    sandbox_deps = [
        d
        for d in _kinds(docs, "Deployment")
        if "mcp-sandbox" in d.get("metadata", {}).get("name", "")
    ]
    assert sandbox_deps, "expected sandbox orchestrator/worker Deployments"
    for dep in sandbox_deps:
        env = dep["spec"]["template"]["spec"]["containers"][0]["env"]
        names = {item["name"]: item.get("value") for item in env}
        assert names.get("SANDBOX_EXECUTION_LOG_ENABLED") == "true"
        assert names.get("SANDBOX_INCLUDE_STDOUT_PREVIEW") == "true"
        assert names.get("SANDBOX_SUSPICIOUS_ON_PROBE_PLUS_ERROR") == "true"


def test_sandbox_worker_token_from_secret():
    proc = _helm("--set", "mcp.sandboxMCP.workerToken=unit-token")
    assert proc.returncode == 0, proc.stderr
    docs = _docs(proc.stdout)
    secrets = [d for d in _kinds(docs, "Secret") if d["metadata"]["name"] == "zelkor-platform-sandbox-worker"]
    assert secrets and secrets[0]["stringData"]["token"] == "unit-token"
    sandbox_deps = [
        d
        for d in _kinds(docs, "Deployment")
        if "mcp-sandbox" in d.get("metadata", {}).get("name", "")
    ]
    assert sandbox_deps
    for dep in sandbox_deps:
        env = dep["spec"]["template"]["spec"]["containers"][0]["env"]
        token = next(item for item in env if item["name"] == "SANDBOX_WORKER_TOKEN")
        assert token["valueFrom"]["secretKeyRef"] == {
            "name": "zelkor-platform-sandbox-worker",
            "key": "token",
        }


def test_node_selector_applies_to_installer_and_runtimeclass():
    proc = _helm(
        "--set",
        r"security.sandbox.nodes.selector.zelkor\.io/sandbox=true",
    )
    assert proc.returncode == 0, proc.stderr
    docs = _docs(proc.stdout)
    ds = _gvisor_ds(docs)
    assert ds is not None
    assert ds["spec"]["template"]["spec"]["nodeSelector"]["zelkor.io/sandbox"] in (True, "true")
    rc = _gvisor_rc(docs)
    assert rc is not None
    assert rc["scheduling"]["nodeSelector"]["zelkor.io/sandbox"] in (True, "true")
