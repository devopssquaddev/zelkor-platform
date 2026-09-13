"""Helm render of databases.mode (no cluster)."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "charts" / "zelkor-platform"
PRODUCTION = ROOT / "profiles" / "values-production.yaml"

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


def test_in_cluster_basic_emits_sts_not_operator_crs():
    proc = _helm("--set", "databases.mode=in-cluster-basic")
    assert proc.returncode == 0, proc.stderr
    docs = _docs(proc.stdout)
    names_sts = _names(docs, "StatefulSet")
    assert "zelkor-platform-postgresql" in names_sts
    assert "zelkor-platform-clickhouse" in names_sts
    assert "zelkor-platform-qdrant" in names_sts
    assert not _kinds(docs, "Cluster")
    assert not _kinds(docs, "ClickHouseInstallation")
    assert "zelkor-platform-valkey" in _names(docs, "Deployment")
    assert "zelkor-platform-seaweedfs" in _names(docs, "Deployment")


def test_clickhouse_26_8_sets_langfuse_datetime_compat():
    basic = _helm("--set", "databases.mode=in-cluster-basic")
    assert basic.returncode == 0, basic.stderr
    assert "26.8.2.7-alpine" in basic.stdout
    assert "input_format_read_datetime_number_as_raw_value" in basic.stdout
    op = _helm("--set", "databases.mode=operator-cr")
    assert op.returncode == 0, op.stderr
    assert "26.8.2.7-alpine" in op.stdout
    assert "input_format_read_datetime_number_as_raw_value" in op.stdout


def test_operator_cr_emits_crs_and_first_party_valkey_qdrant():
    proc = _helm("--set", "databases.mode=operator-cr")
    assert proc.returncode == 0, proc.stderr
    docs = _docs(proc.stdout)
    sts = _names(docs, "StatefulSet")
    assert "zelkor-platform-postgresql" not in sts
    assert "zelkor-platform-clickhouse" not in sts
    assert "zelkor-platform-qdrant" in sts
    clusters = _kinds(docs, "Cluster")
    assert clusters
    assert clusters[0]["apiVersion"] == "postgresql.cnpg.io/v1"
    assert clusters[0]["spec"]["instances"] == 1
    assert clusters[0]["spec"]["imageName"] == "ghcr.io/cloudnative-pg/postgresql:16.15"
    assert (
        clusters[0]["spec"]["inheritedMetadata"]["labels"]["app.kubernetes.io/component"]
        == "postgresql"
    )
    assert any(
        "OWNER" in sql for sql in clusters[0]["spec"]["bootstrap"]["initdb"]["postInitSQL"]
    )
    aliases = [
        d
        for d in _kinds(docs, "Service")
        if d["metadata"]["name"] == "zelkor-platform-postgresql"
        and d["spec"].get("type") == "ExternalName"
    ]
    assert aliases
    assert "zelkor-platform-postgresql-rw.zelkor.svc.cluster.local" in aliases[0]["spec"]["externalName"]
    chi = _kinds(docs, "ClickHouseInstallation")
    assert chi
    assert chi[0]["apiVersion"] == "clickhouse.altinity.com/v1"
    assert "zelkor-platform-valkey" in _names(docs, "Deployment")
    assert "zelkor-platform-seaweedfs" in _names(docs, "Deployment")
    assert "ObjectStore" not in {d.get("kind") for d in docs}


def test_production_overlay_is_operator_cr_without_dev_literals():
    proc = _helm("-f", str(PRODUCTION))
    assert proc.returncode == 0, proc.stderr
    assert "localhost" not in proc.stdout
    assert "dev-key" not in proc.stdout
    assert "trustTenantHeader: true" not in proc.stdout
    docs = _docs(proc.stdout)
    clusters = _kinds(docs, "Cluster")
    assert clusters[0]["spec"]["instances"] == 3
    assert not _kinds(docs, "ObjectStore")
    nps = _kinds(docs, "NetworkPolicy")
    assert nps


def test_external_fails_closed_without_hosts():
    proc = _helm("--set", "databases.mode=external")
    assert proc.returncode != 0
    assert "external.host" in proc.stderr


def test_external_emits_neither_sts_nor_crs():
    proc = _helm(
        "--set",
        "databases.mode=external",
        "--set",
        "databases.postgresql.external.host=pg.example.svc",
        "--set",
        "databases.clickhouse.external.host=ch.example.svc",
        "--set",
        "databases.valkey.external.host=vk.example.svc",
    )
    assert proc.returncode == 0, proc.stderr
    docs = _docs(proc.stdout)
    sts = _names(docs, "StatefulSet")
    assert "zelkor-platform-postgresql" not in sts
    assert "zelkor-platform-clickhouse" not in sts
    assert "zelkor-platform-qdrant" not in sts
    assert not _kinds(docs, "Cluster")
    assert not _kinds(docs, "ClickHouseInstallation")
    assert "zelkor-platform-valkey" not in _names(docs, "Deployment")


def test_barman_requires_destination():
    proc = _helm("--set", "databases.mode=operator-cr", "--set", "databases.postgresql.barman.enabled=true")
    assert proc.returncode != 0
    assert "destinationPath" in proc.stderr


def test_envoyproxy_clusterip_has_no_kind_nodeselector():
    proc = _helm(
        "--set",
        "gateway.envoyProxy.enabled=true",
        "--set",
        "gateway.envoyProxy.service.type=ClusterIP",
    )
    assert proc.returncode == 0, proc.stderr
    docs = _docs(proc.stdout)
    proxies = _kinds(docs, "EnvoyProxy")
    assert proxies
    rendered = proc.stdout
    assert "ingress-ready" not in rendered
    k8s = proxies[0]["spec"]["provider"]["kubernetes"]
    assert k8s["envoyService"]["type"] == "ClusterIP"
    assert k8s["envoyService"]["name"] == "zelkor-zelkor-platform-dataplane"
    patch = k8s["envoyDeployment"]["patch"]["value"]
    spec = ((patch.get("spec") or {}).get("template") or {}).get("spec") or {}
    assert "ingress-ready" not in str(spec.get("nodeSelector") or {})
    assert spec.get("hostNetwork") is not True


def test_envoyproxy_local_overlay_keeps_kind_nodeselector():
    proc = _helm("-f", str(ROOT / "profiles" / "values-local.yaml"))
    assert proc.returncode == 0, proc.stderr
    docs = _docs(proc.stdout)
    proxies = _kinds(docs, "EnvoyProxy")
    assert proxies
    spec = proxies[0]["spec"]["provider"]["kubernetes"]["envoyDeployment"]["patch"]["value"]["spec"]["template"]["spec"]
    assert spec["nodeSelector"]["ingress-ready"] == "true"
    assert spec["hostNetwork"] is True
    k8s = proxies[0]["spec"]["provider"]["kubernetes"]
    assert "envoyService" not in k8s or not (k8s.get("envoyService") or {}).get("type")


def test_attach_skips_gatewayclass_and_uses_parent_ref():
    proc = _helm(
        "--set",
        "gateway.createGatewayClass=false",
        "--set",
        "gateway.createGateway=false",
        "--set",
        "gateway.parentRef.name=their-gw",
        "--set",
        "gateway.parentRef.namespace=envoy-system",
        "--set",
        "gateway.envoyProxy.enabled=true",
        "--set",
        "gateway.hosts.agents=agents.example.com",
        "--set",
        "gateway.hosts.langfuse=langfuse.example.com",
    )
    assert proc.returncode == 0, proc.stderr
    docs = _docs(proc.stdout)
    assert not _kinds(docs, "GatewayClass")
    assert not _kinds(docs, "Gateway")
    assert not _kinds(docs, "EnvoyProxy")
    routes = _kinds(docs, "HTTPRoute")
    names = {d["metadata"]["name"] for d in routes}
    assert "zelkor-platform-mcp-gateway-route" not in names
    assert "zelkor-platform-nemo-route" not in names
    parents = []
    for route in routes:
        for ref in route["spec"]["parentRefs"]:
            parents.append((ref["name"], ref.get("namespace")))
    assert ("their-gw", "envoy-system") in parents
    assert all(p[0] != "zelkor-platform-gateway" for p in parents)


def test_gateway_layered_profile_emits_clusterip():
    proc = _helm("-f", str(ROOT / "profiles" / "values-gateway-layered.yaml"))
    assert proc.returncode == 0, proc.stderr
    docs = _docs(proc.stdout)
    proxies = _kinds(docs, "EnvoyProxy")
    assert proxies
    k8s = proxies[0]["spec"]["provider"]["kubernetes"]
    assert k8s["envoyService"]["type"] == "ClusterIP"
    assert k8s["envoyService"]["name"] == "zelkor-zelkor-platform-dataplane"
    ai_svc = next(
        d
        for d in _kinds(docs, "Service")
        if d["metadata"]["name"] == "zelkor-platform-ai-gateway"
    )
    assert ai_svc["spec"]["externalName"] == (
        "zelkor-zelkor-platform-dataplane.envoy-gateway-system.svc.cluster.local"
    )


def test_gateway_shared_profile_attaches_to_parent_ref():
    proc = _helm(
        "-f",
        str(ROOT / "profiles" / "values-gateway-shared.yaml"),
        "--set",
        "gateway.parentRef.name=their-gw",
        "--set",
        "gateway.parentRef.namespace=envoy-system",
        "--set",
        "gateway.hosts.agents=agents.example.com",
        "--set",
        "gateway.hosts.langfuse=langfuse.example.com",
    )
    assert proc.returncode == 0, proc.stderr
    docs = _docs(proc.stdout)
    assert not _kinds(docs, "GatewayClass")
    assert not _kinds(docs, "Gateway")
    assert not _kinds(docs, "EnvoyProxy")
    parents = []
    for route in _kinds(docs, "HTTPRoute"):
        for ref in route["spec"]["parentRefs"]:
            parents.append((ref["name"], ref.get("namespace")))
    assert ("their-gw", "envoy-system") in parents


def test_empty_optional_hosts_emit_no_public_mcp_nemo_v1():
    proc = _helm(
        "--set",
        "gateway.hosts.agents=agents.example.com",
        "--set",
        "gateway.hosts.langfuse=langfuse.example.com",
    )
    assert proc.returncode == 0, proc.stderr
    docs = _docs(proc.stdout)
    names = _names(docs, "HTTPRoute")
    assert "zelkor-platform-mcp-gateway-route" not in names
    assert "zelkor-platform-nemo-route" not in names
    aigw = _kinds(docs, "AIGatewayRoute")
    for route in aigw:
        hosts = route.get("spec", {}).get("hostnames") or []
        assert not any("ai-gateway." in h and "svc.cluster.local" not in h and h != "zelkor-platform-ai-gateway" for h in hosts)


def test_langfuse_admin_secret_and_job():
    proc = _helm("-f", str(PRODUCTION))
    assert proc.returncode == 0, proc.stderr
    docs = _docs(proc.stdout)
    secrets = [
        d
        for d in _kinds(docs, "Secret")
        if d["metadata"]["name"] == "zelkor-platform-langfuse-admin"
    ]
    assert secrets
    data = secrets[0].get("stringData") or {}
    assert data["email"] == "admin@langfuse.example.com"
    assert data["name"] == "Admin"
    assert data["password"]
    jobs = [d for d in _kinds(docs, "Job") if d["metadata"]["name"] == "zelkor-platform-langfuse-admin"]
    assert jobs
    admin_ann = (jobs[0].get("metadata") or {}).get("annotations") or {}
    assert "helm.sh/hook" not in admin_ann
    env = {
        e["name"]: e
        for e in jobs[0]["spec"]["template"]["spec"]["containers"][0]["env"]
    }
    assert env["SEED_ADMIN"]["value"] == "true"
    ref = env["LANGFUSE_ADMIN_PASSWORD"]["valueFrom"]["secretKeyRef"]
    assert ref["name"] == "zelkor-platform-langfuse-admin"
    assert ref["key"] == "password"
    values = (CHART / "values.yaml").read_text()
    assert "zelkor-dev-password" not in values
    assert "admin@zelkor.local" not in values


def test_langfuse_admin_disabled_emits_nothing():
    proc = _helm("--set", "langfuse.admin.enabled=false")
    assert proc.returncode == 0, proc.stderr
    docs = _docs(proc.stdout)
    assert "zelkor-platform-langfuse-admin" not in _names(docs, "Secret")
    assert "zelkor-platform-langfuse-admin" not in _names(docs, "Job")


def test_langfuse_admin_existing_secret_skips_generated_secret():
    proc = _helm("--set", "langfuse.admin.existingSecret=customer-langfuse-admin")
    assert proc.returncode == 0, proc.stderr
    docs = _docs(proc.stdout)
    assert "zelkor-platform-langfuse-admin" not in _names(docs, "Secret")
    jobs = [d for d in _kinds(docs, "Job") if d["metadata"]["name"] == "zelkor-platform-langfuse-admin"]
    assert jobs
    env = {
        e["name"]: e
        for e in jobs[0]["spec"]["template"]["spec"]["containers"][0]["env"]
    }
    assert env["LANGFUSE_ADMIN_PASSWORD"]["valueFrom"]["secretKeyRef"]["name"] == "customer-langfuse-admin"


@pytest.mark.parametrize("flag", ["--help", "-h"])
def test_bootstrap_operators_help(flag: str):
    script = ROOT / "scripts" / "bootstrap-operators.sh"
    proc = subprocess.run(["bash", str(script), flag], check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert "--skip-cnpg" in proc.stdout
    assert "ESO" in proc.stdout or "Valkey" in proc.stdout
