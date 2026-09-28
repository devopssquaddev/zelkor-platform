"""K11 control 1: zelkor-gateway-policies chart (offline helm template)."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "charts" / "zelkor-gateway-policies"


def _helm(*extra: str) -> subprocess.CompletedProcess[str]:
    cmd = [
        "helm",
        "template",
        "zelkor-gateway-policies",
        str(CHART),
        "--namespace",
        "envoy-gateway-system",
    ]
    cmd.extend(extra)
    return subprocess.run(cmd, check=False, capture_output=True, text=True)


def _docs(rendered: str) -> list[dict]:
    return [d for d in yaml.safe_load_all(rendered) if d]


def _np(docs: list[dict]) -> dict:
    for doc in docs:
        if doc.get("kind") == "NetworkPolicy":
            return doc
    raise AssertionError("NetworkPolicy not found")


def test_requires_gateway_name():
    proc = _helm(
        "--set",
        "gateway.namespace=zelkor",
        "--set",
        "listeners[0].port=80",
    )
    assert proc.returncode != 0
    assert "gateway.name" in proc.stderr


def test_empty_listeners_fail_render():
    proc = _helm(
        "--set",
        "gateway.name=zelkor-platform-gateway",
        "--set",
        "gateway.namespace=zelkor",
    )
    assert proc.returncode != 0
    assert "listeners must not be empty" in proc.stderr


def test_listener_ports_map_below_1024_and_preserve_high_ports():
    proc = _helm(
        "--set",
        "gateway.name=zelkor-platform-gateway",
        "--set",
        "gateway.namespace=zelkor",
        "--set",
        "listeners[0].port=80",
        "--set",
        "listeners[1].port=8443",
    )
    assert proc.returncode == 0, proc.stderr
    spec = _np(_docs(proc.stdout))["spec"]
    ports = sorted(p["port"] for rule in spec["ingress"] for p in rule["ports"])
    assert ports == [8443, 10080, 19003]


def test_owning_gateway_pod_selector_not_generic_envoy_label():
    proc = _helm(
        "--set",
        "gateway.name=my-gw",
        "--set",
        "gateway.namespace=team-a",
        "--set",
        "listeners[0]=80",
    )
    assert proc.returncode == 0, proc.stderr
    labels = _np(_docs(proc.stdout))["spec"]["podSelector"]["matchLabels"]
    assert labels == {
        "gateway.envoyproxy.io/owning-gateway-name": "my-gw",
        "gateway.envoyproxy.io/owning-gateway-namespace": "team-a",
    }
    assert "app.kubernetes.io/name" not in labels


def test_implicit_deny_admin_port_9856():
    proc = _helm(
        "--set",
        "gateway.name=zelkor-platform-gateway",
        "--set",
        "gateway.namespace=zelkor",
        "--set",
        "listeners[0].port=80",
    )
    assert proc.returncode == 0, proc.stderr
    spec = _np(_docs(proc.stdout))["spec"]
    ports = {p["port"] for rule in spec["ingress"] for p in rule["ports"]}
    assert 9856 not in ports


def test_monitoring_ports_only_with_namespace_selector():
    proc = _helm(
        "--set",
        "gateway.name=zelkor-platform-gateway",
        "--set",
        "gateway.namespace=zelkor",
        "--set",
        "listeners[0].port=80",
        "--set",
        "monitoring.namespaceSelector.kubernetes\\.io/metadata\\.name=monitoring",
    )
    assert proc.returncode == 0, proc.stderr
    spec = _np(_docs(proc.stdout))["spec"]
    assert len(spec["ingress"]) == 2
    mon_ports = {p["port"] for p in spec["ingress"][1]["ports"]}
    assert mon_ports == {19001, 1064}
