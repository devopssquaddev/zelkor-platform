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
    "platform.tenants.jwt.issuer=https://issuer.example",
    "platform.tenants.jwt.audiences[0]=zelkor",
    "platform.tenants.jwt.remoteJwksUri=https://issuer.example/.well-known/jwks.json",
    "security.mcp.acceptUnprotectedBackends=true",
    "postgresql.auth.password=test-pg",
    "clickhouse.auth.password=test-ch",
    "seaweedfs.auth.accessKey=test-ak",
    "seaweedfs.auth.secretKey=test-sk",
    "platform.telemetry.langfuse.nextauthSecret=test-na",
    "platform.telemetry.langfuse.salt=test-salt-1234567890",
    "platform.telemetry.langfuse.encryptionKey=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    "platform.telemetry.langfuse.nextauthUrl=https://langfuse.example.com",
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
