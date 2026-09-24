"""Helm render of CE-4 Path B HA, Gateway TLS, and ServiceMonitors (no cluster)."""
from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "charts" / "zelkor-platform"
AGENT = ROOT / "charts" / "zelkor-agent"
PRODUCTION = ROOT / "profiles" / "values-production.yaml"
FINSERVE_VALUES = ROOT / "examples" / "finserve" / "chart" / "values.yaml"

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

HA_DEPLOYMENTS = (
    "zelkor-platform-aegra",
    "zelkor-platform-langfuse",
    "zelkor-platform-langfuse-worker",
    "zelkor-platform-nemo",
    "zelkor-platform-mcp-gateway",
    "zelkor-platform-mcp-postgres",
    "zelkor-platform-mcp-qdrant",
    "zelkor-platform-mcp-egress",
    "zelkor-platform-mcp-sandbox",
)

SM_SERVICES = (
    "zelkor-platform-aegra",
    "zelkor-platform-nemo",
    "zelkor-platform-mcp-gateway",
    "zelkor-platform-mcp-postgres",
    "zelkor-platform-mcp-qdrant",
    "zelkor-platform-mcp-egress",
    "zelkor-platform-mcp-sandbox",
    "zelkor-platform-qdrant",
)

AGENT_SETS = [
    "graphId=demo-graph",
    "platform.databaseUrl=postgres://zelkor:x@pg:5432/aegra",
    "platform.valkeyUrl=redis://vk:6379/0",
]


def _helm(*extra: str) -> subprocess.CompletedProcess[str]:
    cmd = ["helm", "template", "zelkor-platform", str(CHART), "--namespace", "zelkor"]
    for item in SECRET_SETS:
        cmd.extend(["--set", item])
    cmd.extend(extra)
    return subprocess.run(cmd, check=False, capture_output=True, text=True)


def _helm_agent(*extra: str) -> subprocess.CompletedProcess[str]:
    cmd = ["helm", "template", "demo-agent", str(AGENT), "--namespace", "zelkor"]
    for item in AGENT_SETS:
        cmd.extend(["--set", item])
    cmd.extend(extra)
    return subprocess.run(cmd, check=False, capture_output=True, text=True)


def _docs(rendered: str) -> list[dict]:
    return [d for d in yaml.safe_load_all(rendered) if d]


def _kinds(docs: list[dict], kind: str) -> list[dict]:
    return [d for d in docs if d.get("kind") == kind]


def _named(docs: list[dict], kind: str, name: str) -> dict:
    matches = [d for d in _kinds(docs, kind) if d["metadata"]["name"] == name]
    assert matches, f"missing {kind}/{name}"
    return matches[0]


def _env(deploy: dict, name: str) -> str | None:
    env = deploy["spec"]["template"]["spec"]["containers"][0].get("env") or []
    for item in env:
        if item.get("name") == name:
            return item.get("value")
    return None


def test_postgres_url_percent_encodes_password():
    proc = _helm("--set", "postgresql.auth.password=p@ss&word")
    assert proc.returncode == 0, proc.stderr
    docs = _docs(proc.stdout)
    langfuse = _named(docs, "Deployment", "zelkor-platform-langfuse")
    db_url = _env(langfuse, "DATABASE_URL")
    assert db_url is not None
    assert "p%40ss%26word" in db_url
    assert "p@ss&word" not in db_url


def test_default_chart_has_no_hpa_https_or_servicemonitor():
    proc = _helm()
    assert proc.returncode == 0, proc.stderr
    docs = _docs(proc.stdout)
    assert not _kinds(docs, "HorizontalPodAutoscaler")
    assert not _kinds(docs, "ServiceMonitor")
    assert not _kinds(docs, "PodMonitor")
    gw = _named(docs, "Gateway", "zelkor-platform-gateway")
    protocols = {lis["protocol"] for lis in gw["spec"]["listeners"]}
    assert protocols == {"HTTP"}
    assert "ClusterIssuer" not in {d.get("kind") for d in docs}
    aegra = _named(docs, "Deployment", "zelkor-platform-aegra")
    assert aegra["spec"]["replicas"] == 1
    assert _env(aegra, "ENABLE_PROMETHEUS_METRICS") == "false"


def test_production_overlay_uses_semver_not_dev():
    proc = _helm("-f", str(PRODUCTION))
    assert proc.returncode == 0, proc.stderr
    assert "ghcr.io/devopssquaddev/zelkor-aegra@sha256:" in proc.stdout
    assert "ghcr.io/devopssquaddev/zelkor-mcp@sha256:" in proc.stdout
    assert "ghcr.io/devopssquaddev/zelkor-guardrails@sha256:" in proc.stdout
    assert "zelkor-aegra:dev" not in proc.stdout
    assert "zelkor-mcp:dev" not in proc.stdout


def test_production_overlay_emits_hpa_and_envoy_hpa():
    proc = _helm("-f", str(PRODUCTION))
    assert proc.returncode == 0, proc.stderr
    assert "localhost" not in proc.stdout
    assert "dev-key" not in proc.stdout
    docs = _docs(proc.stdout)
    hpa_names = {d["metadata"]["name"] for d in _kinds(docs, "HorizontalPodAutoscaler")}
    assert set(HA_DEPLOYMENTS) <= hpa_names
    for name in HA_DEPLOYMENTS:
        deploy = _named(docs, "Deployment", name)
        assert "replicas" not in deploy["spec"], name
    qdrant = _named(docs, "StatefulSet", "zelkor-platform-qdrant")
    assert qdrant["spec"]["replicas"] == 1
    workers = [
        d
        for d in _kinds(docs, "Deployment")
        if d["metadata"]["name"].startswith("zelkor-platform-mcp-sandbox-worker-")
    ]
    assert len(workers) == 3
    assert all(w["spec"]["replicas"] == 1 for w in workers)
    proxies = _kinds(docs, "EnvoyProxy")
    assert proxies
    hpa = proxies[0]["spec"]["provider"]["kubernetes"]["envoyHpa"]
    assert hpa["minReplicas"] == 2
    assert hpa["maxReplicas"] == 8
    assert proxies[0]["spec"]["provider"]["kubernetes"]["envoyService"]["name"] == (
        "zelkor-zelkor-platform-dataplane"
    )
    lf_hpa = _named(docs, "HorizontalPodAutoscaler", "zelkor-platform-langfuse")
    assert lf_hpa["spec"]["minReplicas"] == 1
    aegra_hpa = _named(docs, "HorizontalPodAutoscaler", "zelkor-platform-aegra")
    assert aegra_hpa["spec"]["minReplicas"] == 2
    worker_hpa = _named(docs, "HorizontalPodAutoscaler", "zelkor-platform-langfuse-worker")
    assert worker_hpa["spec"]["minReplicas"] == 2
    ai_svc = _named(docs, "Service", "zelkor-platform-ai-gateway")
    assert ai_svc["spec"]["type"] == "ExternalName"
    assert ai_svc["spec"]["externalName"] == (
        "zelkor-zelkor-platform-dataplane.envoy-gateway-system.svc.cluster.local"
    )
    assert not _kinds(docs, "ServiceMonitor")


def test_production_overlay_ha_off_omits_hpa():
    proc = _helm("-f", str(PRODUCTION), "--set", "highAvailability.enabled=false")
    assert proc.returncode == 0, proc.stderr
    docs = _docs(proc.stdout)
    assert not _kinds(docs, "HorizontalPodAutoscaler")
    aegra = _named(docs, "Deployment", "zelkor-platform-aegra")
    assert aegra["spec"]["replicas"] == 1
    assert not _kinds(docs, "EnvoyProxy")


def test_gateway_tls_listener_and_cluster_issuer_annotation():
    proc = _helm(
        "--set",
        "gateway.tls.enabled=true",
        "--set",
        "gateway.tls.clusterIssuer=test-issuer",
        "--set",
        "gateway.hosts.agents=agents.example.com",
    )
    assert proc.returncode == 0, proc.stderr
    docs = _docs(proc.stdout)
    assert not _kinds(docs, "ClusterIssuer")
    gw = _named(docs, "Gateway", "zelkor-platform-gateway")
    assert gw["metadata"]["annotations"]["cert-manager.io/cluster-issuer"] == "test-issuer"
    https = [lis for lis in gw["spec"]["listeners"] if lis["protocol"] == "HTTPS"]
    assert len(https) == 1
    assert https[0]["name"] == "https-agents"
    assert https[0]["port"] == 443
    assert https[0]["hostname"] == "agents.example.com"
    assert https[0]["tls"]["mode"] == "Terminate"
    assert https[0]["tls"]["certificateRefs"][0]["name"] == "zelkor-platform-tls-agents"
    http = [lis for lis in gw["spec"]["listeners"] if lis["protocol"] == "HTTP"]
    assert http


def test_service_monitors_opt_in_on_production():
    proc = _helm("-f", str(PRODUCTION), "--set", "observability.serviceMonitor.enabled=true")
    assert proc.returncode == 0, proc.stderr
    docs = _docs(proc.stdout)
    sm_names = {d["metadata"]["name"] for d in _kinds(docs, "ServiceMonitor")}
    assert set(SM_SERVICES) <= sm_names
    assert "zelkor-platform-envoy" in {d["metadata"]["name"] for d in _kinds(docs, "PodMonitor")}
    aegra = _named(docs, "Deployment", "zelkor-platform-aegra")
    assert _env(aegra, "ENABLE_PROMETHEUS_METRICS") == "true"
    nemo = _named(docs, "Deployment", "zelkor-platform-nemo")
    assert _env(nemo, "ENABLE_PROMETHEUS_METRICS") == "true"
    cluster = _kinds(docs, "Cluster")[0]
    assert cluster["spec"]["monitoring"]["enablePodMonitor"] is True
    kinds = {d.get("kind") for d in docs}
    assert "GrafanaDashboard" not in kinds
    assert "Grafana" not in kinds


def test_agent_chart_hpa_default_on():
    proc = _helm_agent()
    assert proc.returncode == 0, proc.stderr
    docs = _docs(proc.stdout)
    hpas = _kinds(docs, "HorizontalPodAutoscaler")
    assert len(hpas) == 1
    deploy = _kinds(docs, "Deployment")[0]
    assert "replicas" not in deploy["spec"]
    assert _env(deploy, "ENABLE_PROMETHEUS_METRICS") == "false"


def test_agent_chart_hpa_off_keeps_replicas():
    proc = _helm_agent("--set", "autoscaling.enabled=false")
    assert proc.returncode == 0, proc.stderr
    docs = _docs(proc.stdout)
    assert not _kinds(docs, "HorizontalPodAutoscaler")
    deploy = _kinds(docs, "Deployment")[0]
    assert deploy["spec"]["replicas"] == 1


def test_finserve_values_disable_agent_autoscaling():
    values = yaml.safe_load(FINSERVE_VALUES.read_text())
    for key in ("desk", "quant", "coder"):
        assert values[key]["autoscaling"]["enabled"] is False
        assert values[key]["replicaCount"] == 1


def test_bootstrap_cert_manager_enables_gateway_api():
    text = (ROOT / "scripts" / "bootstrap-operators.sh").read_text()
    assert "config.enableGatewayAPI=true" in text


def test_metrics_deps_in_images():
    assert "prometheus_client" in (ROOT / "images" / "mcp" / "requirements.txt").read_text()
    guardrails = (ROOT / "images" / "guardrails" / "requirements.txt").read_text()
    assert "prometheus-fastapi-instrumentator" in guardrails
    mcp = (ROOT / "mcp" / "common" / "mcp_server.py").read_text()
    assert "/metrics" in mcp


def test_langfuse_public_route_gated_until_enabled():
    proc = _helm(
        "--set",
        "gateway.hosts.langfuse=langfuse.example.com",
    )
    assert proc.returncode == 0, proc.stderr
    routes = [
        d
        for d in _docs(proc.stdout)
        if d.get("kind") == "HTTPRoute" and d["metadata"]["name"].endswith("-langfuse-route")
    ]
    assert not routes
    proc2 = _helm(
        "--set",
        "gateway.hosts.langfuse=langfuse.example.com",
        "--set",
        "langfuse.publicHttpRoute.enabled=true",
    )
    assert proc2.returncode == 0, proc2.stderr
    routes2 = [
        d
        for d in _docs(proc2.stdout)
        if d.get("kind") == "HTTPRoute" and d["metadata"]["name"].endswith("-langfuse-route")
    ]
    assert len(routes2) == 1


def test_production_profile_renders_langfuse_seed_network_policy():
    proc = _helm("-f", str(PRODUCTION))
    assert proc.returncode == 0, proc.stderr
    docs = _docs(proc.stdout)
    np = _named(docs, "NetworkPolicy", "zelkor-platform-langfuse-bootstrap-egress")
    peers = []
    for rule in (np.get("spec") or {}).get("egress") or []:
        for peer in rule.get("to") or []:
            labels = (peer.get("podSelector") or {}).get("matchLabels") or {}
            peers.append(labels)
    assert any(p.get("app.kubernetes.io/component") == "valkey" for p in peers), peers
    match_labels = (
        ((np.get("spec") or {}).get("podSelector") or {}).get("matchExpressions") or []
    )
    components = next(
        (expr.get("values") or [] for expr in match_labels if expr.get("key") == "app.kubernetes.io/component"),
        [],
    )
    assert components == ["langfuse-bootstrap"]
