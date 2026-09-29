"""C6: zelkor-gateway-policies chart (listener ports, empty listeners)."""
from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "charts" / "zelkor-gateway-policies"


def _helm(*extra: str) -> subprocess.CompletedProcess[str]:
    cmd = [
        "helm",
        "template",
        "zelkor-gw-policies",
        str(CHART),
        "--namespace",
        "envoy-gateway-system",
        "--set",
        "gateway.name=zelkor-gw",
        "--set",
        "gateway.namespace=envoy-gateway-system",
    ]
    cmd.extend(extra)
    return subprocess.run(cmd, check=False, capture_output=True, text=True)


def _ingress_ports(rendered: str) -> list[int]:
    docs = [d for d in yaml.safe_load_all(rendered) if d]
    np = next(d for d in docs if d.get("kind") == "NetworkPolicy")
    ports: list[int] = []
    for rule in np["spec"]["ingress"]:
        for port in rule.get("ports") or []:
            ports.append(int(port["port"]))
    return ports


def test_empty_listeners_fail_render():
    r = _helm("--set", "listeners=")
    assert r.returncode != 0
    assert "listeners" in r.stderr


def test_listeners_map_to_container_ports():
    r = _helm("--set", "listeners[0]=80", "--set", "listeners[1]=8443")
    assert r.returncode == 0, r.stderr
    ports = _ingress_ports(r.stdout)
    assert 10080 in ports
    assert 8443 in ports
    assert 19003 in ports


def test_monitoring_namespace_selector_adds_metrics_ports():
    r = _helm(
        "--set",
        "listeners[0]=80",
        "--set",
        'monitoring.namespaceSelector.kubernetes\\.io/metadata\\.name=monitoring',
    )
    assert r.returncode == 0, r.stderr
    ports = _ingress_ports(r.stdout)
    assert 19001 in ports
    assert 1064 in ports
