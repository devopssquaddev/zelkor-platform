"""Offline checks for existing-cluster CE install wrappers (--dry-run).

Agent install contract: docs/agent-install.md
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
QS = ROOT / "scripts" / "install-quickstart.sh"
PROD = ROOT / "scripts" / "install-production.sh"
UNINSTALL = ROOT / "scripts" / "uninstall.sh"
LIB = ROOT / "scripts" / "lib" / "cluster-install.sh"
INSTALL_LOG = ROOT / "scripts" / "lib" / "install-log.sh"
OWN = ROOT / "scripts" / "lib" / "bootstrap-ownership.sh"
GW = ROOT / "scripts" / "bootstrap-gateway.sh"
OPS = ROOT / "scripts" / "bootstrap-operators.sh"


def _run(script: Path, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    full_env = {
        "PATH": __import__("os").environ.get("PATH", ""),
        "HOME": __import__("os").environ.get("HOME", "/tmp"),
        "OPENAI_API_KEY": "sk-test-cluster-install",
        "INSTALL_LOG_FILE": "off",
    }
    if env:
        full_env.update(env)
    return subprocess.run(
        [str(script), *args],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env=full_env,
    )


def test_scripts_bash_n():
    for path in (LIB, INSTALL_LOG, OWN, QS, PROD, UNINSTALL, GW, OPS):
        proc = subprocess.run(["bash", "-n", str(path)], check=False, capture_output=True, text=True)
        assert proc.returncode == 0, f"{path}: {proc.stderr}"


def test_quickstart_dry_run_greenfield():
    proc = _run(QS, "--dry-run", "--namespace", "zelkor-play")
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    assert "BOOTSTRAP_GATEWAY" in out
    assert "bootstrap-gateway.sh" in out
    assert "--skip-envoy-gateway" not in out
    assert "HELM" in out
    assert "values-quickstart.yaml" in out
    assert "values-gateway-greenfield.yaml" in out
    assert "values-local.yaml" not in out
    assert "workspace.models.providers.openai.apiKey=sk-test-cluster-install" in out
    assert "workspace.models.consumerKey=" in out
    assert "gateway.hosts.agents=agents.zelkor-play.zelkor.local" in out
    assert "gateway.hosts.langfuse=langfuse.zelkor-play.zelkor.local" in out
    assert "postgresql.auth.password=" in out
    assert "workspace.tools.sandboxMCP.workerToken=" in out


def test_quickstart_dry_run_layered():
    proc = _run(QS, "--dry-run", "--topology", "layered")
    assert proc.returncode == 0, proc.stderr
    assert "values-gateway-layered.yaml" in proc.stdout
    assert "--skip-envoy-gateway" not in proc.stdout


def test_quickstart_dry_run_shared():
    proc = _run(
        QS,
        "--dry-run",
        "--topology",
        "shared",
        "--gateway-class",
        "eg",
        "--parent-ref-name",
        "their-gw",
        "--parent-ref-namespace",
        "envoy-system",
    )
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    assert "values-gateway-shared.yaml" in out
    assert "--skip-envoy-gateway" in out
    assert "--skip-ai-gateway" in out
    assert "gateway.parentRef.name=their-gw" in out
    assert "gateway.gatewayClassName=eg" in out


def test_quickstart_dry_run_shared_install_ai_gateway():
    proc = _run(
        QS,
        "--dry-run",
        "--topology",
        "shared",
        "--install-ai-gateway",
        "--gateway-class",
        "eg",
        "--parent-ref-name",
        "their-gw",
        "--parent-ref-namespace",
        "envoy-system",
    )
    assert proc.returncode == 0, proc.stderr
    assert "--skip-envoy-gateway" in proc.stdout
    assert "--patch-extension-manager" in proc.stdout
    assert "--skip-ai-gateway" not in proc.stdout


def test_quickstart_requires_llm():
    proc = _run(QS, "--dry-run", env={"OPENAI_API_KEY": ""})
    assert proc.returncode != 0
    assert "LLM provider" in proc.stderr or "llm provider" in proc.stderr.lower()


def test_quickstart_dry_run_azure_not_fatal():
    proc = _run(
        QS,
        "--dry-run",
        "--namespace",
        "zelkor-play",
        env={
            "OPENAI_API_KEY": "",
            "AZURE_OPENAI_API_KEY": "az-test",
            "AZURE_OPENAI_ENDPOINT": "https://res.openai.azure.com",
        },
    )
    assert proc.returncode == 0, proc.stderr
    assert "workspace.models.providers.azure.apiKey=az-test" in proc.stdout
    assert "workspace.models.providers.azure.endpoint=https://res.openai.azure.com" in proc.stdout


def test_quickstart_dry_run_bedrock_not_fatal():
    proc = _run(
        QS,
        "--dry-run",
        "--namespace",
        "zelkor-play",
        env={
            "OPENAI_API_KEY": "",
            "AWS_ACCESS_KEY_ID": "AKIATEST",
            "AWS_SECRET_ACCESS_KEY": "secret",
            "AWS_REGION": "eu-west-1",
        },
    )
    assert proc.returncode == 0, proc.stderr
    assert "workspace.models.providers.bedrock.accessKeyId=AKIATEST" in proc.stdout
    assert "workspace.models.providers.bedrock.region=eu-west-1" in proc.stdout


def test_quickstart_dry_run_vertex_not_fatal():
    proc = _run(
        QS,
        "--dry-run",
        "--namespace",
        "zelkor-play",
        env={
            "OPENAI_API_KEY": "",
            "VERTEX_PROJECT": "my-proj",
            "VERTEX_REGION": "us-central1",
        },
    )
    assert proc.returncode == 0, proc.stderr
    assert "workspace.models.providers.vertex.project=my-proj" in proc.stdout
    assert "workspace.models.providers.vertex.region=us-central1" in proc.stdout


def test_quickstart_shared_requires_parent_ref():
    proc = _run(QS, "--dry-run", "--topology", "shared")
    assert proc.returncode != 0
    assert "parent-ref" in proc.stderr


def test_production_dry_run_greenfield():
    proc = _run(
        PROD,
        "--dry-run",
        "--hosts-agents",
        "agents.example.com",
        "--hosts-langfuse",
        "langfuse.example.com",
        "--generate-passwords",
    )
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    assert "BOOTSTRAP_OPERATORS" in out
    assert "bootstrap-operators.sh" in out
    assert "BOOTSTRAP_GATEWAY" in out
    assert "values-production.yaml" in out
    assert "values-gateway-greenfield.yaml" in out
    assert "values-local.yaml" not in out
    assert "gateway.hosts.agents=agents.example.com" in out
    assert "platform.telemetry.langfuse.nextauthUrl=https://langfuse.example.com" in out
    assert "postgresql.auth.password=" in out
    assert "workspace.tools.sandboxMCP.workerToken=" in out
    assert "Generated install secrets" in out
    assert "workspace.models.providers.openai.apiKey=sk-test-cluster-install" in out


def _printed_secret(stdout: str, name: str) -> str:
    prefix = f"  {name}="
    for line in stdout.splitlines():
        if line.startswith(prefix):
            return line[len(prefix) :]
    raise AssertionError(f"{name} not printed in Generated install secrets block")


def test_production_generated_url_secrets_are_hex():
    """Postgres/ClickHouse passwords must be URL-safe (Langfuse migration URLs)."""
    proc = _run(
        PROD,
        "--dry-run",
        "--hosts-agents",
        "agents.example.com",
        "--hosts-langfuse",
        "langfuse.example.com",
        "--generate-passwords",
    )
    assert proc.returncode == 0, proc.stderr
    for name in (
        "POSTGRES_PASSWORD",
        "CLICKHOUSE_PASSWORD",
        "VALKEY_PASSWORD",
        "SEAWEEDFS_ACCESS_KEY",
        "SEAWEEDFS_SECRET_KEY",
    ):
        value = _printed_secret(proc.stdout, name)
        assert value, name
        assert all(c in "0123456789abcdef" for c in value), f"{name}={value!r} is not hex"
    worker = _printed_secret(proc.stdout, "WORKER_TOKEN")
    assert worker
    # Bearer token may stay base64; must not be forced through the hex URL-safe path alone.
    assert len(worker) >= 32


def test_production_dry_run_skip_operators_and_tls():
    proc = _run(
        PROD,
        "--dry-run",
        "--skip-operators",
        "--topology",
        "layered",
        "--hosts-agents",
        "agents.example.com",
        "--hosts-langfuse",
        "langfuse.example.com",
        "--generate-passwords",
        "--tls",
        "--cluster-issuer",
        "letsencrypt-prod",
        "--service-monitor",
    )
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    assert "BOOTSTRAP_OPERATORS" not in out
    assert "values-gateway-layered.yaml" in out
    assert "gateway.tls.enabled=true" in out
    assert "gateway.tls.clusterIssuer=letsencrypt-prod" in out
    assert "observability.serviceMonitor.enabled=true" in out


def test_production_image_pull_secret_quoted():
    proc = _run(
        PROD,
        "--dry-run",
        "--hosts-agents",
        "agents.example.com",
        "--hosts-langfuse",
        "langfuse.example.com",
        "--generate-passwords",
        "--image-pull-secret",
        "private-registry",
    )
    assert proc.returncode == 0, proc.stderr
    assert "global.imagePullSecrets[0].name=private-registry" in proc.stdout


def test_refuse_foreign_eg_allows_layered():
    script = f"""
    set -euo pipefail
    ZELKOR_REPO_ROOT={ROOT}
    source {LIB}
    cluster_install_init
    CLUSTER_INSTALL_TOPOLOGY=layered
    CLUSTER_INSTALL_DRY_RUN=0
    cluster_install_deployment_available() {{ return 0; }}
    cluster_install_eg_owned() {{ return 1; }}
    cluster_install_refuse_foreign_eg
    echo ok
    """
    proc = subprocess.run(["bash", "-c", script], check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "ok"


def test_refuse_foreign_eg_greenfield_dies():
    script = f"""
    set -euo pipefail
    ZELKOR_REPO_ROOT={ROOT}
    source {LIB}
    cluster_install_init
    CLUSTER_INSTALL_TOPOLOGY=greenfield
    CLUSTER_INSTALL_DRY_RUN=0
    cluster_install_deployment_available() {{ return 0; }}
    cluster_install_eg_owned() {{ return 1; }}
    cluster_install_refuse_foreign_eg
    echo should-not-reach
    """
    proc = subprocess.run(["bash", "-c", script], check=False, capture_output=True, text=True)
    assert proc.returncode != 0
    assert "already running" in proc.stderr
    assert "should-not-reach" not in proc.stdout


def test_production_dry_run_generates_secrets_without_flag():
    proc = _run(
        PROD,
        "--dry-run",
        "--hosts-agents",
        "agents.example.com",
        "--hosts-langfuse",
        "langfuse.example.com",
    )
    assert proc.returncode == 0, proc.stderr
    assert "postgresql.auth.password=" in proc.stdout
    assert "workspace.tools.sandboxMCP.workerToken=" in proc.stdout
    assert "workspace.models.consumerKey=" in proc.stdout
    assert "Generated install secrets" not in proc.stdout


def test_production_rejects_localhost_hosts():
    proc = _run(
        PROD,
        "--dry-run",
        "--hosts-agents",
        "agents.localhost",
        "--hosts-langfuse",
        "langfuse.localhost",
        "--generate-passwords",
    )
    assert proc.returncode != 0
    assert "localhost" in proc.stderr


def test_production_requires_hosts():
    proc = _run(PROD, "--dry-run", "--generate-passwords")
    assert proc.returncode != 0
    assert "hosts-agents" in proc.stderr


def test_eg_patch_action_foreign_ready_fails_without_flag():
    script = f"""
    source {OWN}
    zelkor_eg_patch_action 1 0 0 0
    """
    proc = subprocess.run(["bash", "-c", script], check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "fail"


def test_eg_patch_action_owned_or_fresh_applies():
    script = f"""
    source {OWN}
    zelkor_eg_patch_action 0 0 0 0
    echo ---
    zelkor_eg_patch_action 1 1 0 0
    echo ---
    zelkor_eg_patch_action 1 0 1 0
    """
    proc = subprocess.run(["bash", "-c", script], check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.split() == ["apply", "---", "apply", "---", "apply"]


def test_uninstall_dry_run_default():
    proc = _run(UNINSTALL, "--dry-run")
    assert proc.returncode == 0, proc.stderr
    assert "HELM_UNINSTALL" in proc.stdout
    assert "helm uninstall zelkor-platform" in proc.stdout
    assert "PURGE_GATEWAY" not in proc.stdout
    assert "PURGE_OPERATORS" not in proc.stdout
    assert "cert-manager" not in proc.stdout


def test_uninstall_purge_operators_respects_ownership():
    proc = _run(
        UNINSTALL,
        "--dry-run",
        "--purge-operators",
        env={"ZELKOR_BOOTSTRAP_OWNERSHIP": "cnpg", "OPENAI_API_KEY": "sk-test-cluster-install"},
    )
    assert proc.returncode == 0, proc.stderr
    assert "PURGE_OPERATORS" in proc.stdout
    assert "helm uninstall cnpg" in proc.stdout
    assert "helm uninstall cert-manager" not in proc.stdout
    assert "SKIP_UNOWNED clickhouse-operator" in proc.stdout


def test_uninstall_purge_gateway_skips_unowned():
    proc = _run(
        UNINSTALL,
        "--dry-run",
        "--purge-gateway",
        env={"KUBECONFIG": "/nonexistent/kubeconfig-for-offline-uninstall-test"},
    )
    assert proc.returncode == 0, proc.stderr
    assert "SKIP_UNOWNED envoy-gateway" in proc.stdout
    assert "SKIP_UNOWNED ai-gateway" in proc.stdout
    assert "install.yaml" not in proc.stdout


def test_uninstall_force_purge_gateway():
    proc = _run(UNINSTALL, "--dry-run", "--purge-gateway", "--force-purge")
    assert proc.returncode == 0, proc.stderr
    assert "SKIP_UNOWNED" not in proc.stdout
    assert "PURGE_GATEWAY" in proc.stdout
    assert "install.yaml" in proc.stdout
    assert "helm uninstall aieg" in proc.stdout


def test_uninstall_purge_cert_manager_owned():
    proc = _run(
        UNINSTALL,
        "--dry-run",
        "--purge-cert-manager",
        env={"ZELKOR_BOOTSTRAP_OWNERSHIP": "cert-manager", "OPENAI_API_KEY": "sk-test-cluster-install"},
    )
    assert proc.returncode == 0, proc.stderr
    assert "PURGE_CERT_MANAGER" in proc.stdout
    assert "helm uninstall cert-manager" in proc.stdout


def test_uninstall_delete_namespace():
    proc = _run(UNINSTALL, "--dry-run", "--delete-namespace", "--namespace", "zelkor-play")
    assert proc.returncode == 0, proc.stderr
    assert "DELETE_NAMESPACE" in proc.stdout
    assert "zelkor-play" in proc.stdout
