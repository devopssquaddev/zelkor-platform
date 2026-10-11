"""Discover Path B pods/services for CE-8c attacker tests."""
from __future__ import annotations

import json
import os
from typing import Any

import pytest

from tests.helpers.kube import kubectl_run

NS = os.environ.get("ZELKOR_PLATFORM_NAMESPACE", "zelkor")


def _require_kube() -> None:
    if not os.environ.get("KUBECONFIG", "").strip():
        pytest.skip("KUBECONFIG not set")


def _json(args: list[str], *, namespace: str | None = NS) -> dict[str, Any]:
    _require_kube()
    res = kubectl_run(args, namespace=namespace, timeout=30)
    if res.returncode != 0:
        pytest.skip(res.stderr or res.stdout or "kubectl failed")
    try:
        return json.loads(res.stdout or "{}")
    except json.JSONDecodeError as exc:
        pytest.skip(f"kubectl JSON parse failed: {exc}")


def running_pod_names(*, label: str) -> list[str]:
    data = _json(["get", "pods", "-l", label, "-o", "json"])
    names: list[str] = []
    for item in data.get("items") or []:
        phase = (item.get("status") or {}).get("phase")
        name = (item.get("metadata") or {}).get("name") or ""
        if phase == "Running" and name:
            names.append(name)
    return names


def _svc_ip_port(item: dict, port: int) -> tuple[str, int] | None:
    ip = (item.get("spec") or {}).get("clusterIP") or ""
    if not ip or ip == "None":
        return None
    ports = (item.get("spec") or {}).get("ports") or []
    for p in ports:
        if int(p.get("port") or 0) == port:
            return ip, port
    if ports:
        return ip, int(ports[0].get("port") or port)
    return None


def service_cluster_ip(name_substring: str, port: int) -> tuple[str, int] | None:
    data = _json(["get", "svc", "-o", "json"])
    for item in data.get("items") or []:
        name = (item.get("metadata") or {}).get("name") or ""
        if name_substring not in name:
            continue
        found = _svc_ip_port(item, port)
        if found:
            return found
    return None


def service_by_component(component: str, port: int) -> tuple[str, int] | None:
    data = _json(["get", "svc", "-l", f"app.kubernetes.io/component={component}", "-o", "json"])
    for item in data.get("items") or []:
        found = _svc_ip_port(item, port)
        if found:
            return found
    return None


def network_policies_enabled() -> bool:
    data = _json(["get", "networkpolicy", "-o", "json"])
    names = [(i.get("metadata") or {}).get("name") or "" for i in data.get("items") or []]
    return any("agent-egress" in n for n in names)


def agent_pod() -> str:
    names = running_pod_names(label="zelkor.io/workload-type=agent")
    if not names:
        pytest.skip("no Running pod with zelkor.io/workload-type=agent")
    return names[0]


def sandbox_mcp_pod() -> str:
    names = running_pod_names(label="app.kubernetes.io/component=mcp-sandbox")
    if not names:
        pytest.skip("no Running mcp-sandbox pod")
    return names[0]


def worker_service() -> tuple[str, int]:
    found = service_cluster_ip("mcp-sandbox-worker-0", 8081)
    if not found:
        pytest.skip("no mcp-sandbox-worker-0 Service")
    return found


def s09_targets() -> list[tuple[str, int, str]]:
    out: list[tuple[str, int, str]] = []
    mapping = (
        ("qdrant", 6333, "qdrant"),
        ("mcp-sandbox-worker", 8081, "worker"),
    )
    for component, port, label in mapping:
        found = service_by_component(component, port)
        if found:
            out.append((found[0], found[1], label))
    extra = os.environ.get("MCP_EXTRA_BACKEND_HOST", "").strip()
    extra_port = os.environ.get("MCP_EXTRA_BACKEND_PORT", "").strip()
    if extra and extra_port:
        out.append((extra, int(extra_port), "extra-mcp"))
    out.append(("1.1.1.1", 443, "public-ip"))
    if not out:
        pytest.skip("no S-09 TCP targets discovered")
    return out


def s10_from_pods() -> list[str]:
    raw = os.environ.get("ZELKOR_TEST_BYPASS_FROM", "")
    if raw.strip():
        return [p.strip() for p in raw.split(",") if p.strip()]
    names = running_pod_names(label="app.kubernetes.io/component=mcp-sandbox-worker")
    if not names:
        pytest.skip("ZELKOR_TEST_BYPASS_FROM unset and no sandbox-worker pods")
    return names


def s10_targets() -> list[tuple[str, int]]:
    raw = os.environ.get("ZELKOR_TEST_BYPASS_TARGETS", "")
    if raw.strip():
        out: list[tuple[str, int]] = []
        for part in raw.split(","):
            part = part.strip()
            if not part:
                continue
            host, port_s = part.rsplit(":", 1)
            out.append((host, int(port_s)))
        return out
    out: list[tuple[str, int]] = []
    for needle, port in (
        ("mcp-postgres", 8080),
        ("mcp-qdrant", 8080),
        ("mcp-sandbox", 8080),
    ):
        found = service_cluster_ip(needle, port)
        if found:
            out.append(found)
    envoy = _envoy_9856()
    if envoy:
        out.append(envoy)
    if not out:
        pytest.skip("ZELKOR_TEST_BYPASS_TARGETS unset and no MCP/Envoy targets")
    return out


def _envoy_9856() -> tuple[str, int] | None:
    data = _json(
        ["get", "pods", "-l", "app.kubernetes.io/name=envoy", "-o", "json"],
        namespace="envoy-gateway-system",
    )
    for item in data.get("items") or []:
        if (item.get("status") or {}).get("phase") != "Running":
            continue
        ip = (item.get("status") or {}).get("podIP") or ""
        if ip:
            return ip, 9856
    return None


def exec_python(pod: str, script: str, *, timeout: int = 20, site: bool = False) -> str:
    py = ["python3", "-c", script] if site else ["python3", "-S", "-c", script]
    res = kubectl_run(["exec", pod, "--", *py], timeout=timeout)
    if res.returncode != 0:
        pytest.skip(res.stderr or res.stdout or f"exec {pod} failed")
    return (res.stdout or "").strip()
