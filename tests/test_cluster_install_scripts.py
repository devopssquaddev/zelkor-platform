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
MCP_DP = ROOT / "scripts" / "lib" / "mcp-dataplane-install.sh"
INSTALL_LOG = ROOT / "scripts" / "lib" / "install-log.sh"
OWN = ROOT / "scripts" / "lib" / "bootstrap-ownership.sh"
GW = ROOT / "scripts" / "bootstrap-gateway.sh"
OPS = ROOT / "scripts" / "bootstrap-operators.sh"

PROD_JWKS = ROOT / "tests" / "fixtures" / "customer-tenant-jwks.json"
PROD_JWT_ARGS = (
    "--jwt-issuer",
    "https://customer.example",
    "--jwt-audience",
    "zelkor",
    "--jwks-file",
    str(PROD_JWKS),
)


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
    for path in (
        LIB,
        MCP_DP,
        INSTALL_LOG,
        OWN,
        QS,
        PROD,
        UNINSTALL,
        GW,
        OPS,
        ROOT / "scripts" / "lib" / "local-signing-helm-sets.sh",
    ):
        proc = subprocess.run(["bash", "-n", str(path)], check=False, capture_output=True, text=True)
        assert proc.returncode == 0, f"{path}: {proc.stderr}"


def test_bootstrap_operators_skips_on_helm_deployed_not_crd_only():
    text = OPS.read_text()
    assert "helm_release_deployed" in text
    assert "skip CNPG: CRD" not in text
    assert "Helm release cnpg already deployed" in text
    assert "HELM_INSTALL_TIMEOUT" in GW.read_text()


def test_local_signing_append_applies_auth_token_for_kind_profile(tmp_path):
    values = tmp_path / "values.yaml"
    values.write_text(
        """
platform:
  tenants:
    jwt:
      issuer: https://local.zelkor.invalid
      audiences: [zelkor]
      localSigning:
        enabled: true
        seedTenant: seed
        seedTokenTTL: 24h
""",
        encoding="utf-8",
    )
    env = {
        "ZELKOR_REPO_ROOT": str(ROOT),
        "HELM_RELEASE_NAME": "zelkor-platform-test",
        "ZELKOR_JWT_STATE_DIR": str(tmp_path / "jwt-state"),
        "HOME": str(tmp_path),
    }
    script = ROOT / "scripts" / "lib" / "local-signing-helm-sets.sh"
    proc = subprocess.run(
        [
            "bash",
            "-c",
            f'source "{script}"; HELM_EXTRA_ARGS=(); append_local_signing_helm_sets HELM_EXTRA_ARGS "{values}"; '
            f'printf "%s\\n" "${{HELM_EXTRA_ARGS[@]}}"',
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env={**__import__("os").environ, **env, "INSTALL_LOG_FILE": "off"},
    )
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout + proc.stderr
    assert "platform.tenants.jwt.localSigning.privateKey=" in out
    assert "platform.telemetry.langfuse.surfaces.tools.authToken=" in out



def test_quickstart_dry_run_greenfield():
    proc = _run(QS, "--skip-gvisor", "--dry-run", "--namespace", "zelkor-play")
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
    proc = _run(QS, "--skip-gvisor", "--dry-run", "--topology", "layered")
    assert proc.returncode == 0, proc.stderr
    assert "values-gateway-layered.yaml" in proc.stdout
    assert "--skip-envoy-gateway" not in proc.stdout


def test_quickstart_dry_run_shared():
    proc = _run(
        QS,
        "--skip-gvisor",
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
        "--skip-gvisor",
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
    proc = _run(QS, "--skip-gvisor", "--dry-run", env={"OPENAI_API_KEY": ""})
    assert proc.returncode != 0
    assert "LLM provider" in proc.stderr or "llm provider" in proc.stderr.lower()


def test_quickstart_dry_run_azure_not_fatal():
    proc = _run(
        QS,
        "--skip-gvisor",
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
        "--skip-gvisor",
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
        "--skip-gvisor",
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
    proc = _run(QS, "--skip-gvisor", "--dry-run", "--topology", "shared")
    assert proc.returncode != 0
    assert "parent-ref" in proc.stderr


def test_production_dry_run_greenfield():
    proc = _run(
        PROD,
        "--skip-gvisor",
        "--dry-run",
        "--hosts-agents",
        "agents.example.com",
        "--hosts-langfuse",
        "langfuse.example.com",
        "--generate-passwords",
        *PROD_JWT_ARGS,
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
    assert "platform.tenants.jwt.issuer=https://customer.example" in out
    assert "--set-string platform.tenants.jwt.audiences[0]=zelkor" in out
    assert "platform.tenants.jwt.jwks=" in out
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
        "--skip-gvisor",
        "--dry-run",
        "--hosts-agents",
        "agents.example.com",
        "--hosts-langfuse",
        "langfuse.example.com",
        "--generate-passwords",
        *PROD_JWT_ARGS,
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
        "--skip-gvisor",
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
        *PROD_JWT_ARGS,
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
        "--skip-gvisor",
        "--dry-run",
        "--hosts-agents",
        "agents.example.com",
        "--hosts-langfuse",
        "langfuse.example.com",
        "--generate-passwords",
        "--image-pull-secret",
        "private-registry",
        *PROD_JWT_ARGS,
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
        "--skip-gvisor",
        "--dry-run",
        "--hosts-agents",
        "agents.example.com",
        "--hosts-langfuse",
        "langfuse.example.com",
        *PROD_JWT_ARGS,
    )
    assert proc.returncode == 0, proc.stderr
    assert "postgresql.auth.password=" in proc.stdout
    assert "workspace.tools.sandboxMCP.workerToken=" in proc.stdout
    assert "workspace.models.consumerKey=" in proc.stdout
    assert "Generated install secrets" not in proc.stdout


def test_production_rejects_localhost_hosts():
    proc = _run(
        PROD,
        "--skip-gvisor",
        "--dry-run",
        "--hosts-agents",
        "agents.localhost",
        "--hosts-langfuse",
        "langfuse.localhost",
        "--generate-passwords",
    )
    assert proc.returncode != 0
    assert "localhost" in proc.stderr


def test_production_requires_jwt():
    proc = _run(
        PROD,
        "--skip-gvisor",
        "--dry-run",
        "--hosts-agents",
        "agents.example.com",
        "--hosts-langfuse",
        "langfuse.example.com",
    )
    assert proc.returncode != 0
    assert "jwt-issuer" in proc.stderr or "localSigning" in proc.stderr


def test_production_requires_hosts():
    proc = _run(PROD, "--skip-gvisor", "--dry-run", "--generate-passwords")
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


def _write_exe(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)


def _lib_bash(body: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    script = f"""
set -euo pipefail
export ZELKOR_REPO_ROOT="{ROOT}"
source "{LIB}"
cluster_install_init
{body}
"""
    full = {
        "PATH": __import__("os").environ.get("PATH", ""),
        "HOME": __import__("os").environ.get("HOME", "/tmp"),
        "INSTALL_LOG_FILE": "off",
        "CLUSTER_INSTALL_RETRY_SLEEP": "0",
    }
    if env:
        full.update(env)
    return subprocess.run(
        ["bash", "-c", script],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env=full,
    )


_KUBECTL_MOCK = r"""#!/usr/bin/env python3
import os, sys
args = sys.argv[1:]
log = os.environ.get("MOCK_KUBECTL_LOG", "")
if log:
    with open(log, "a", encoding="utf-8") as fh:
        fh.write(" ".join(args) + "\n")
if not args or args[0] != "get" or len(args) < 2:
    sys.stderr.write("unexpected kubectl %s\n" % args)
    sys.exit(99)
kind = args[1]
rest = args[2:]
name = rest[0] if rest and not rest[0].startswith("-") else ""
if kind == "storageclass":
    if name:
        prov = os.environ.get("MOCK_PROVISIONER_" + name, os.environ.get("MOCK_PROVISIONER", "csi.example.com"))
        sys.stdout.write(prov)
        sys.exit(0)
    sys.stdout.write(os.environ.get("MOCK_DEFAULT_SC", "") + "\n")
    sys.exit(0)
if kind == "csidriver":
    sys.exit(0 if os.environ.get("MOCK_IS_CSI", "1") == "1" else 1)
if kind == "nodes":
    if "go-template" in " ".join(args):
        sys.stdout.write(os.environ.get("MOCK_NODE_LABELS", ""))
        sys.exit(0)
    sys.stdout.write(os.environ.get("MOCK_NODES", "n1 True\nn2 True\nn3 True\n"))
    sys.exit(0)
if kind == "csinode":
    joined = " ".join(args)
    if "go-template" in joined:
        sys.stdout.write(os.environ.get("MOCK_CSI_TOPOLOGY", ""))
        sys.exit(0)
    sys.stdout.write(os.environ.get("MOCK_CSINODES", ""))
    sys.exit(0)
if kind == "pods":
    sys.stdout.write(os.environ.get("MOCK_PODS", ""))
    sys.exit(0)
sys.stderr.write("unexpected kubectl %s\n" % args)
sys.exit(99)
"""

_HELM_MOCK = r"""#!/usr/bin/env python3
import os, sys
args = sys.argv[1:]
log = os.environ["MOCK_HELM_LOG"]
with open(log, "a", encoding="utf-8") as fh:
    fh.write(" ".join(args) + "\n")
state = os.environ["MOCK_HELM_STATE"]
stuck = os.environ.get("MOCK_HELM_STUCK", "0") == "1"

def read_state():
    try:
        return open(state, encoding="utf-8").read().strip() or "deployed"
    except FileNotFoundError:
        return "deployed"

def write_state(value):
    with open(state, "w", encoding="utf-8") as fh:
        fh.write(value)

if "status" in args:
    print("STATUS: %s" % read_state())
    sys.exit(0)
if "rollback" in args:
    if not stuck:
        write_state("deployed")
    print("rollback ok")
    sys.exit(0)
if "uninstall" in args:
    write_state("uninstalled")
    sys.exit(0)
if "upgrade" in args:
    count_path = state + ".n"
    n = 0
    if os.path.exists(count_path):
        n = int(open(count_path, encoding="utf-8").read() or "0")
    n += 1
    with open(count_path, "w", encoding="utf-8") as fh:
        fh.write(str(n))
    if stuck or n == 1:
        write_state("pending-upgrade")
        sys.stderr.write("EOF\n")
        sys.exit(1)
    write_state("deployed")
    print("upgrade ok")
    sys.exit(0)
sys.stderr.write("unexpected helm %s\n" % args)
sys.exit(99)
"""


def _kubectl_env(tmp_path: Path, **overrides: str) -> dict[str, str]:
    import os

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_exe(bin_dir / "kubectl", _KUBECTL_MOCK)
    env = {
        "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}",
        "MOCK_KUBECTL_LOG": str(tmp_path / "kubectl.log"),
        "MOCK_DEFAULT_SC": "local-disk",
        "MOCK_PROVISIONER": "csi.example.com",
        "MOCK_IS_CSI": "1",
        "MOCK_NODES": "n1 True\nn2 True\nn3 True\n",
        "MOCK_CSINODES": "n1\tcsi.example.com \nn2\tcsi.example.com \nn3\tcsi.example.com \n",
        "MOCK_PODS": "",
    }
    env.update(overrides)
    return env


def test_storage_mixed_explicit_class_fails(tmp_path: Path):
    env = _kubectl_env(tmp_path)
    proc = _lib_bash(
        """
CLUSTER_INSTALL_PG_INSTANCES=3
CLUSTER_INSTALL_HELM_SETS=(--set databases.postgresql.storage.storageClass=fast)
cluster_install_storage_preflight
echo should-not-reach
""",
        env=env,
    )
    assert proc.returncode != 0
    assert "should-not-reach" not in proc.stdout
    err = proc.stderr
    assert "empty for others" in err
    assert "--set databases.clickhouse.storage.storageClass" in err
    assert "--set seaweedfs.persistence.storageClass" in err
    assert "databases.postgresql.storage.storageClass=fast" not in err
    log = (tmp_path / "kubectl.log").read_text(encoding="utf-8") if (tmp_path / "kubectl.log").exists() else ""
    assert log == ""


def test_storage_instances_exceed_nodes_that_advertise_class(tmp_path: Path):
    env = _kubectl_env(
        tmp_path,
        MOCK_CSINODES="n1\tcsi.example.com \nn2\tother.driver \nn3\tother.driver \n",
    )
    proc = _lib_bash(
        """
CLUSTER_INSTALL_PG_INSTANCES=3
cluster_install_storage_preflight
echo should-not-reach
""",
        env=env,
    )
    assert proc.returncode != 0, proc.stderr
    assert "should-not-reach" not in proc.stdout
    assert "--set databases.postgresql.instances=1" in proc.stderr
    assert "local-disk" in proc.stderr


def test_storage_topology_label_without_driver_fails(tmp_path: Path):
    env = _kubectl_env(
        tmp_path,
        MOCK_CSI_TOPOLOGY="n1\tcsi.example.com\tcsi.example.com/location \nn2\tother.driver\t\n",
        MOCK_NODE_LABELS="n1\tcsi.example.com/location \nn2\tcsi.example.com/location \nn3\tkubernetes.io/hostname \n",
    )
    proc = _lib_bash(
        """
CLUSTER_INSTALL_PG_INSTANCES=1
cluster_install_storage_preflight
echo should-not-reach
""",
        env=env,
    )
    assert proc.returncode != 0, proc.stderr
    assert "should-not-reach" not in proc.stdout
    assert "do not list the CSIDriver" in proc.stderr
    assert "databases.postgresql.storage.storageClass" in proc.stderr
    assert "n2" in proc.stderr


def test_storage_default_class_on_enough_nodes_passes(tmp_path: Path):
    env = _kubectl_env(tmp_path)
    proc = _lib_bash(
        """
CLUSTER_INSTALL_PG_INSTANCES=3
cluster_install_storage_preflight
echo ok
""",
        env=env,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip().endswith("ok")


def test_helm_failure_rolls_back_pending_upgrade(tmp_path: Path):
    import os

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_exe(bin_dir / "helm", _HELM_MOCK)
    state = tmp_path / "helm-state"
    log = tmp_path / "helm.log"
    env = {
        "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}",
        "MOCK_HELM_LOG": str(log),
        "MOCK_HELM_STATE": str(state),
        "MOCK_HELM_STUCK": "0",
    }
    proc = _lib_bash(
        """
CLUSTER_INSTALL_RETRY_SLEEP=0
cluster_install_helm_with_recovery helm upgrade --install zelkor-platform
echo RECOVERY_OK
""",
        env=env,
    )
    assert proc.returncode == 0, proc.stderr
    assert "RECOVERY_OK" in proc.stdout
    text = log.read_text(encoding="utf-8")
    assert "rollback" in text
    assert state.read_text(encoding="utf-8").strip() == "deployed"

    stuck_state = tmp_path / "helm-stuck"
    stuck_log = tmp_path / "helm-stuck.log"
    env["MOCK_HELM_STATE"] = str(stuck_state)
    env["MOCK_HELM_LOG"] = str(stuck_log)
    env["MOCK_HELM_STUCK"] = "1"
    stuck = _lib_bash(
        """
CLUSTER_INSTALL_RETRY_SLEEP=0
cluster_install_helm_with_recovery helm upgrade --install zelkor-platform
echo should-not-reach
""",
        env=env,
    )
    assert stuck.returncode != 0
    assert "should-not-reach" not in stuck.stdout
    assert "pending-upgrade" in stuck.stderr
    assert "helm rollback" in stuck.stderr
    assert "rollback" in stuck_log.read_text(encoding="utf-8")


def test_layered_dataplane_banner_prints_ingress_and_health():
    proc = _lib_bash(
        """
CLUSTER_INSTALL_TOPOLOGY=layered
CLUSTER_INSTALL_NEXTAUTH_SCHEME=https
HOSTS_AGENTS=agents.example.com
HOSTS_LANGFUSE=langfuse.example.com
cluster_install_print_dataplane
"""
    )
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    assert "networking.k8s.io/v1" in out
    assert "kind: Ingress" in out
    assert "namespace: envoy-gateway-system" in out
    assert "zelkor-zelkor-platform-dataplane" in out
    assert "number: 80" in out
    assert "agents.example.com" in out
    assert "langfuse.example.com" in out
    assert "https://agents.example.com/health" in out
    assert "https://langfuse.example.com/api/public/health" in out
    assert "cert-manager" not in out
    assert "traefik" not in out.lower()


def test_production_help_mentions_storage_instances_and_health():
    proc = _run(PROD, "--help")
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    assert "databases.postgresql.storage.storageClass" in out
    assert "databases.clickhouse.storage.storageClass" in out
    assert "seaweedfs.persistence.storageClass" in out
    assert "databases.postgresql.instances" in out
    assert "/health" in out
    assert "/api/public/health" in out
    assert "--install-gvisor" in out
    assert "--skip-gvisor" in out


def test_gvisor_preflight_does_not_adopt_unowned_runtimeclass(tmp_path: Path):
    import os

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_exe(
        bin_dir / "kubectl",
        r"""#!/usr/bin/env python3
import sys
args = sys.argv[1:]
joined = " ".join(args)
if args[:1] == ["cluster-info"]:
    sys.exit(0)
if args[:2] == ["get", "nodes"] and "sandbox.gke.io/runtime=gvisor" in joined:
    sys.exit(0)
if args[:2] == ["get", "nodes"] and "containerRuntimeVersion" in joined:
    print("containerd://1.7.0")
    sys.exit(0)
if args[:2] == ["delete", "pod"]:
    sys.exit(0)
if args[:1] == ["apply"]:
    sys.exit(0)
if args[:3] == ["get", "pod", "zelkor-gvisor-preflight-smoke"]:
    print("Succeeded")
    sys.exit(0)
if args[:2] == ["get", "runtimeclass"] and "release-name" in joined:
    sys.stdout.write("")
    sys.exit(0)
if args[:2] == ["get", "runtimeclass"] and "release-namespace" in joined:
    sys.stdout.write("")
    sys.exit(0)
if args[:2] == ["get", "runtimeclass"]:
    sys.exit(0)
sys.stderr.write("unexpected %s\n" % args)
sys.exit(99)
""",
    )
    env = {
        "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}",
        "GVISOR_HELM_RELEASE": "zelkor-platform",
        "GVISOR_HELM_NAMESPACE": "zelkor",
    }
    proc = subprocess.run(
        [str(ROOT / "scripts" / "gvisor-preflight.sh"), "--output", "helm"],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env={**os.environ, **env, "INSTALL_LOG_FILE": "off"},
    )
    assert proc.returncode == 0, proc.stderr
    assert "security.sandbox.createRuntimeClass=false" in proc.stdout
    assert "will not adopt" in proc.stderr


def test_gvisor_preflight_without_opt_in_does_not_choose_daemonset(tmp_path: Path):
    import os

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_exe(
        bin_dir / "kubectl",
        r"""#!/usr/bin/env python3
import sys
args = sys.argv[1:]
joined = " ".join(args)
if args[:1] == ["cluster-info"]:
    sys.exit(0)
if args[:2] == ["get", "nodes"] and "sandbox.gke.io/runtime=gvisor" in joined:
    sys.exit(0)
if args[:2] == ["get", "nodes"] and "containerRuntimeVersion" in joined:
    print("containerd://1.7.0")
    sys.exit(0)
if args[:2] == ["get", "runtimeclass"]:
    sys.exit(1)
sys.stderr.write("unexpected %s\n" % args)
sys.exit(99)
""",
    )
    env = {"PATH": f"{bin_dir}:{os.environ.get('PATH', '')}"}
    proc = subprocess.run(
        [str(ROOT / "scripts" / "gvisor-preflight.sh"), "--output", "helm"],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env={**os.environ, **env, "INSTALL_LOG_FILE": "off"},
    )
    assert proc.returncode == 0, proc.stderr
    assert "security.sandbox.provisioning.mode=none" in proc.stdout
    opted = subprocess.run(
        [str(ROOT / "scripts" / "gvisor-preflight.sh"), "--output", "helm"],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env={**os.environ, **env, "INSTALL_LOG_FILE": "off", "GVISOR_INSTALL_OPT_IN": "true"},
    )
    assert opted.returncode == 0, opted.stderr
    assert "security.sandbox.provisioning.mode=daemonset" in opted.stdout


def test_gvisor_choose_refuses_empty_selector_on_multi_node(tmp_path: Path):
    import os

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_exe(
        bin_dir / "kubectl",
        r"""#!/usr/bin/env python3
import sys
args = sys.argv[1:]
if args[:2] == ["get", "nodes"]:
    sys.stdout.write("node-a\nnode-b\n")
    sys.exit(0)
sys.exit(0)
""",
    )
    proc = _lib_bash(
        """
CLUSTER_INSTALL_GVISOR_INSTALL=1
CLUSTER_INSTALL_DRY_RUN=0
cluster_install_gvisor_choose
""",
        env={"PATH": f"{bin_dir}:{os.environ.get('PATH', '')}"},
    )
    assert proc.returncode != 0
    err = proc.stderr
    assert "node-a" in err
    assert "node-b" in err
    assert "sandbox pool" in err


def test_gvisor_choose_allows_one_node_without_selector(tmp_path: Path):
    import os

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_exe(
        bin_dir / "kubectl",
        r"""#!/usr/bin/env python3
import sys
if sys.argv[1:3] == ["get", "nodes"]:
    sys.stdout.write("only-node\n")
    sys.exit(0)
sys.exit(0)
""",
    )
    proc = _lib_bash(
        """
CLUSTER_INSTALL_GVISOR_INSTALL=1
CLUSTER_INSTALL_DRY_RUN=0
cluster_install_gvisor_choose
printf '%s\n' "${CLUSTER_INSTALL_HELM_SETS[@]}"
""",
        env={"PATH": f"{bin_dir}:{os.environ.get('PATH', '')}"},
    )
    assert proc.returncode == 0, proc.stderr
    assert "only-node" in proc.stdout
    assert "restart the container runtime" in proc.stdout
    assert "security.sandbox.provisioning.mode=daemonset" in proc.stdout


def test_gvisor_choose_without_flag_exits_before_install():
    proc = _lib_bash(
        """
CLUSTER_INSTALL_DRY_RUN=1
cluster_install_gvisor_choose
echo should-not-reach
"""
    )
    assert proc.returncode != 0
    assert "should-not-reach" not in proc.stdout
    assert "--install-gvisor" in proc.stderr
    assert "--skip-gvisor" in proc.stderr


def test_production_dry_run_stays_offline(tmp_path: Path):
    import os

    marker = tmp_path / "kubectl-called"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_exe(
        bin_dir / "kubectl",
        f"#!/bin/sh\ntouch {marker}\necho kubectl-called >&2\nexit 97\n",
    )
    proc = _run(
        PROD,
        "--skip-gvisor",
        "--dry-run",
        "--hosts-agents",
        "agents.example.com",
        "--hosts-langfuse",
        "langfuse.example.com",
        *PROD_JWT_ARGS,
        env={"PATH": f"{bin_dir}:{os.environ.get('PATH', '')}"},
    )
    assert proc.returncode == 0, proc.stderr
    assert not marker.exists()
    assert "HELM" in proc.stdout
