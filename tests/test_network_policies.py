"""C6 network policies: MCP controls 2/3 and platform global flag independence (offline)."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "charts" / "zelkor-platform"
QUICKSTART = ROOT / "profiles" / "values-quickstart.yaml"
GREENFIELD = ROOT / "profiles" / "values-gateway-greenfield.yaml"

SECRET_SETS = [
    "security.mcp.acceptUnprotectedBackends=true",
    "postgresql.auth.password=test-pg",
    "clickhouse.auth.password=test-ch",
    "seaweedfs.auth.accessKey=test-ak",
    "seaweedfs.auth.secretKey=test-sk",
    "platform.telemetry.langfuse.nextauthSecret=test-na",
    "platform.telemetry.langfuse.salt=test-salt-1234567890",
    "platform.telemetry.langfuse.encryptionKey=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    "platform.telemetry.langfuse.nextauthUrl=https://langfuse.example.com",
    "gateway.envoyProxy.enabled=true",
]

PLATFORM_NAMESPACE = os.environ.get("ZELKOR_PLATFORM_NAMESPACE", "default")


def _helm(*extra: str) -> subprocess.CompletedProcess[str]:
    cmd = ["helm", "template", "zelkor-platform", str(CHART), "--namespace", "zelkor"]
    for item in SECRET_SETS:
        cmd.extend(["--set", item])
    cmd.extend(extra)
    return subprocess.run(cmd, check=False, capture_output=True, text=True)


def _docs(rendered: str) -> list[dict]:
    return [d for d in yaml.safe_load_all(rendered) if d]


def _named(docs: list[dict], kind: str, substring: str) -> dict | None:
    for doc in docs:
        if doc.get("kind") != kind:
            continue
        if substring in doc["metadata"]["name"]:
            return doc
    return None


def test_mcp_backend_ingress_and_worker_egress_with_global_np_disabled():
    proc = _helm(
        "-f",
        str(QUICKSTART),
        "-f",
        str(GREENFIELD),
        "--set",
        "security.networkPolicies.enabled=false",
        "--set",
        "security.mcp.acceptUnprotectedBackends=false",
    )
    assert proc.returncode == 0, proc.stderr
    docs = _docs(proc.stdout)
    backend = _named(docs, "NetworkPolicy", "mcp-backend-ingress")
    assert backend is not None
    assert backend["spec"]["ingress"][0]["ports"] == [{"port": 8080}]
    worker = _named(docs, "NetworkPolicy", "sandbox-worker-egress")
    assert worker is not None
    assert worker["spec"]["egress"] == []


def test_accept_unprotected_backends_skips_control_3():
    proc = _helm(
        "-f",
        str(QUICKSTART),
        "--set",
        "security.networkPolicies.enabled=false",
        "--set",
        "security.mcp.acceptUnprotectedBackends=true",
    )
    assert proc.returncode == 0, proc.stderr
    docs = _docs(proc.stdout)
    assert _named(docs, "NetworkPolicy", "mcp-backend-ingress") is None
    assert _named(docs, "NetworkPolicy", "sandbox-worker-egress") is not None


def test_mcp_metrics_ingress_when_servicemonitor_enabled():
    proc = _helm(
        "-f",
        str(QUICKSTART),
        "-f",
        str(GREENFIELD),
        "--set",
        "security.networkPolicies.enabled=false",
        "--set",
        "security.mcp.acceptUnprotectedBackends=false",
        "--set",
        "observability.serviceMonitor.enabled=true",
        "--set",
        "observability.monitoringNamespaceSelector.kubernetes\\.io/metadata\\.name=monitoring",
    )
    assert proc.returncode == 0, proc.stderr
    backend = _named(_docs(proc.stdout), "NetworkPolicy", "mcp-backend-ingress")
    assert backend is not None
    ports = [rule["ports"] for rule in backend["spec"]["ingress"]]
    assert [{"port": 8080}] in ports
    assert [{"port": 9090}] in ports


def test_mcp_deployments_expose_metrics_port_9090():
    proc = _helm("-f", str(QUICKSTART), "-f", str(GREENFIELD))
    assert proc.returncode == 0, proc.stderr
    for component in ("mcp-postgres", "mcp-qdrant", "mcp-sandbox", "mcp-aigateway"):
        deploys = [
            d
            for d in _docs(proc.stdout)
            if d.get("kind") == "Deployment" and d["metadata"]["name"].endswith(component)
        ]
        assert deploys, component
        container = deploys[0]["spec"]["template"]["spec"]["containers"][0]
        names = {p.get("name") or str(p["containerPort"]) for p in container["ports"]}
        assert "metrics" in names or 9090 in names
        env = {e["name"]: e["value"] for e in container.get("env", []) if "value" in e}
        assert env.get("MCP_METRICS_PORT") == "9090"


def test_network_policies_present_when_enabled(kubecontext):
    """Path A overlay enables NetworkPolicies; skip when the flag is off."""
    try:
        res = subprocess.run(
            [
                "kubectl",
                "--context",
                kubecontext,
                "get",
                "networkpolicy",
                "-n",
                PLATFORM_NAMESPACE,
                "-o",
                "json",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        pytest.skip(str(exc))
    items = json.loads(res.stdout).get("items") or []
    names = [item["metadata"]["name"] for item in items]
    if not any("agent-egress" in n for n in names):
        pytest.skip("security.networkPolicies.enabled is off in this cluster")
    assert any("mcp-postgres-egress" in n for n in names), names
    assert any("sandbox-worker-ingress" in n for n in names), names
    assert any("aegra-egress" in n for n in names), names
    aegra = next(i for i in items if "aegra-egress" in i["metadata"]["name"])
    peers = []
    for rule in (aegra.get("spec") or {}).get("egress") or []:
        for peer in rule.get("to") or []:
            labels = (peer.get("podSelector") or {}).get("matchLabels") or {}
            peers.append(labels)
    assert not any(p.get("zelkor.io/workload-type") == "agent" for p in peers), peers
    assert any(p.get("app.kubernetes.io/component") == "postgresql" for p in peers), peers


def _peer_ns_labels(policy: dict) -> list[dict]:
    labels: list[dict] = []
    for rule in (policy.get("spec") or {}).get("ingress") or []:
        for peer in rule.get("from") or []:
            sel = (peer.get("namespaceSelector") or {}).get("matchLabels") or {}
            if sel:
                labels.append(sel)
    return labels


def test_dest_deny_absent_when_np_off():
    proc = _helm(
        "-f",
        str(QUICKSTART),
        "--set",
        "security.networkPolicies.enabled=false",
    )
    assert proc.returncode == 0, proc.stderr
    docs = _docs(proc.stdout)
    assert _named(docs, "NetworkPolicy", "default-deny-ingress") is None
    assert _named(docs, "NetworkPolicy", "postgres-dest-deny") is None


def test_dest_deny_kind_hostnetwork_skips_envoy_peer_policies():
    """K17: acceptUnprotectedBackends means Envoy is the node IP; dest-deny must not close MCP/Aegra."""
    proc = _helm(
        "-f",
        str(QUICKSTART),
        "--set",
        "security.networkPolicies.enabled=true",
        "--set",
        "security.mcp.acceptUnprotectedBackends=true",
    )
    assert proc.returncode == 0, proc.stderr
    docs = _docs(proc.stdout)
    deny = _named(docs, "NetworkPolicy", "default-deny-ingress")
    assert deny is not None
    exprs = (deny.get("spec") or {}).get("podSelector", {}).get("matchExpressions") or []
    notin = next((e for e in exprs if e.get("operator") == "NotIn"), None)
    assert notin is not None, deny.get("spec")
    assert "mcp-postgres" in (notin.get("values") or [])
    assert "aegra" in (notin.get("values") or [])
    assert _named(docs, "NetworkPolicy", "aegra-dest-deny") is None
    assert _named(docs, "NetworkPolicy", "langfuse-dest-deny") is None
    assert _named(docs, "NetworkPolicy", "guardrails-dest-deny") is None
    assert _named(docs, "NetworkPolicy", "postgres-dest-deny") is not None


def test_dest_deny_no_cross_ns_when_isolation_off():
    proc = _helm(
        "-f",
        str(QUICKSTART),
        "-f",
        str(GREENFIELD),
        "--set",
        "security.networkPolicies.enabled=true",
        "--set",
        "security.mcp.acceptUnprotectedBackends=false",
        "--set",
        "platform.isolation.agentNamespaces=false",
    )
    assert proc.returncode == 0, proc.stderr
    docs = _docs(proc.stdout)
    deny = _named(docs, "NetworkPolicy", "default-deny-ingress")
    assert deny is not None
    pg = _named(docs, "NetworkPolicy", "postgres-dest-deny")
    assert pg is not None
    ns_labels = _peer_ns_labels(pg)
    assert not any(l.get("zelkor.io/namespace-role") == "agent" for l in ns_labels), ns_labels
    lf = _named(docs, "NetworkPolicy", "langfuse-dest-deny")
    assert lf is not None
    lf_pods = {
        ((peer.get("podSelector") or {}).get("matchLabels") or {}).get("app.kubernetes.io/component")
        for rule in (lf.get("spec") or {}).get("ingress") or []
        for peer in rule.get("from") or []
    }
    assert {"aegra", "guardrails", "langfuse-bootstrap"} <= lf_pods
    qdrant = _named(docs, "NetworkPolicy", "qdrant-dest-deny")
    assert qdrant is not None
    q_labels = {
        ((peer.get("podSelector") or {}).get("matchLabels") or {}).get("zelkor.io/workload-type")
        for rule in (qdrant.get("spec") or {}).get("ingress") or []
        for peer in rule.get("from") or []
    }
    assert "datastore-init" in q_labels
    assert "agent" not in q_labels
    pg_types = {
        ((peer.get("podSelector") or {}).get("matchLabels") or {}).get("zelkor.io/workload-type")
        for rule in (pg.get("spec") or {}).get("ingress") or []
        for peer in rule.get("from") or []
    }
    assert {"agent", "datastore-init"} <= pg_types


def test_dest_deny_isolation_allows_compiled_agent_label():
    proc = _helm(
        "-f",
        str(QUICKSTART),
        "-f",
        str(GREENFIELD),
        "--set",
        "security.networkPolicies.enabled=true",
        "--set",
        "security.mcp.acceptUnprotectedBackends=false",
        "--set",
        "platform.isolation.agentNamespaces=true",
    )
    assert proc.returncode == 0, proc.stderr
    docs = _docs(proc.stdout)
    pg = _named(docs, "NetworkPolicy", "postgres-dest-deny")
    vk = _named(docs, "NetworkPolicy", "valkey-dest-deny")
    aegra = _named(docs, "NetworkPolicy", "aegra-dest-deny")
    assert pg and vk and aegra
    pg_ns = _peer_ns_labels(pg)
    assert any(l.get("zelkor.io/namespace-role") == "agent" for l in pg_ns), pg_ns
    vk_ns = _peer_ns_labels(vk)
    assert any(l.get("zelkor.io/namespace-role") == "agent" for l in vk_ns), vk_ns
    aegra_ns = _peer_ns_labels(aegra)
    assert not any(l.get("zelkor.io/namespace-role") == "agent" for l in aegra_ns), aegra_ns
    qdrant = _named(docs, "NetworkPolicy", "qdrant-dest-deny")
    assert qdrant is not None
    assert not any(l.get("zelkor.io/namespace-role") == "agent" for l in _peer_ns_labels(qdrant))
    lf = _named(docs, "NetworkPolicy", "langfuse-dest-deny")
    assert lf is not None
    lf_pods = [
        ((peer.get("podSelector") or {}).get("matchLabels") or {}).get("app.kubernetes.io/component")
        for rule in (lf.get("spec") or {}).get("ingress") or []
        for peer in rule.get("from") or []
    ]
    assert "aegra" in lf_pods and "guardrails" in lf_pods, lf_pods


def test_dest_deny_operator_peers_when_operator_cr():
    proc = _helm(
        "-f",
        str(QUICKSTART),
        "--set",
        "security.networkPolicies.enabled=true",
        "--set",
        "databases.mode=operator-cr",
    )
    assert proc.returncode == 0, proc.stderr
    docs = _docs(proc.stdout)
    cnpg = _named(docs, "NetworkPolicy", "cnpg-dest-deny")
    assert cnpg is not None
    assert any(
        l.get("kubernetes.io/metadata.name") == "cnpg-system" for l in _peer_ns_labels(cnpg)
    )
