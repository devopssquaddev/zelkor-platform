"""S-29 / P8: unlabeled namespace cannot reach platform datastores (L2 helm + live)."""
from __future__ import annotations

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
]


def _helm(*extra: str) -> str:
    cmd = ["helm", "template", "zelkor-platform", str(CHART), "--namespace", "zelkor"]
    for item in SECRET_SETS:
        cmd.extend(["--set", item])
    cmd.extend(extra)
    res = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    return res.stdout


def _named(rendered: str, kind: str, substring: str) -> dict | None:
    for doc in yaml.safe_load_all(rendered):
        if not doc or doc.get("kind") != kind:
            continue
        if substring in doc["metadata"]["name"]:
            return doc
    return None


def _ns_roles(policy: dict) -> list[str]:
    roles: list[str] = []
    for rule in (policy.get("spec") or {}).get("ingress") or []:
        for peer in rule.get("from") or []:
            labels = (peer.get("namespaceSelector") or {}).get("matchLabels") or {}
            role = labels.get("zelkor.io/namespace-role")
            if role:
                roles.append(role)
    return roles


def test_s29_helm_unlabeled_peer_absent_when_isolation_on():
    rendered = _helm(
        "-f",
        str(QUICKSTART),
        "-f",
        str(GREENFIELD),
        "--set",
        "security.networkPolicies.enabled=true",
        "--set",
        "platform.isolation.agentNamespaces=true",
    )
    pg = _named(rendered, "NetworkPolicy", "postgres-dest-deny")
    assert pg is not None
    roles = _ns_roles(pg)
    assert roles and all(r == "agent" for r in roles)
    empty = [p for p in (pg.get("spec") or {}).get("ingress") or [] for peer in p.get("from") or [] if peer == {}]
    assert not empty


def test_s29_live_unlabeled_ns_refused():
    if not os.environ.get("KUBECONFIG", "").strip():
        pytest.skip("KUBECONFIG not set")
    from tests.helpers.ce8 import network_policies_enabled, service_by_component
    from tests.helpers.kube import kubectl_run

    if not network_policies_enabled():
        pytest.skip("security.networkPolicies.enabled is off")
    ns = os.environ.get("S29_NAMESPACE", "zelkor-s29-unlabeled")
    targets = []
    for component, port in (("postgresql", 5432), ("valkey", 6379), ("qdrant", 6333)):
        found = service_by_component(component, port)
        if found:
            targets.append(found)
    if not targets:
        pytest.skip("no datastore ClusterIPs")
    create = kubectl_run(["create", "namespace", ns], namespace="", timeout=30)
    if create.returncode != 0 and "AlreadyExists" not in (create.stderr or ""):
        pytest.skip(create.stderr or "could not create unlabeled ns")
    try:
        kubectl_run(
            [
                "label",
                "namespace",
                ns,
                "zelkor.io/namespace-role-",
                "--overwrite",
            ],
            namespace="",
            timeout=30,
        )
        run = kubectl_run(
            [
                "run",
                "s29-probe",
                "--restart=Never",
                "--image=python:3.12-alpine",
                "--command",
                "--",
                "python",
                "-c",
                "import socket,sys,time; time.sleep(2); "
                + "; ".join(
                    f"s=socket.socket(); s.settimeout(5); e=s.connect_ex(({ip!r},{port})); s.close(); "
                    f"sys.stdout.write('{ip}:{port}='+str(e)+'\\n')"
                    for ip, port in targets
                ),
            ],
            namespace=ns,
            timeout=30,
        )
        if run.returncode != 0:
            pytest.skip(run.stderr or "could not start probe pod")
        kubectl_run(["wait", "--for=jsonpath={.status.phase}=Succeeded", "pod/s29-probe", "--timeout=60s"], namespace=ns, timeout=70)
        logs = kubectl_run(["logs", "s29-probe"], namespace=ns, timeout=20)
        opened = [line for line in (logs.stdout or "").splitlines() if line.endswith("=0")]
        assert not opened, f"unlabeled ns reached {opened}"
    finally:
        kubectl_run(["delete", "pod", "s29-probe", "--ignore-not-found"], namespace=ns, timeout=30)
        kubectl_run(["delete", "namespace", ns, "--ignore-not-found"], namespace="", timeout=60)
