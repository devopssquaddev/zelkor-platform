"""S-28 / UAT-23: labeled agent-ns worker P8 egress (opt-in live)."""
from __future__ import annotations

import os
import subprocess

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("ARMOR_AGENT") != "gpt-researcher",
    reason="opt-in live armor; set ARMOR_AGENT=gpt-researcher",
)


def _kube(*args: str, namespace: str = "") -> subprocess.CompletedProcess[str]:
    cmd = ["kubectl"]
    kubeconfig = os.environ.get("KUBECONFIG", "").strip()
    if kubeconfig:
        cmd.extend(["--kubeconfig", kubeconfig])
    context = os.environ.get("KUBECONTEXT", "").strip() or os.environ.get("KUBE_CONTEXT", "").strip()
    if context:
        cmd.extend(["--context", context])
    if namespace:
        cmd.extend(["-n", namespace])
    cmd.extend(args)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)


def test_worker_in_labeled_agent_namespace():
    ns = os.getenv("GPTR_NAMESPACE", "gptr")
    got = _kube("get", "ns", ns, "-o", "jsonpath={.metadata.labels.zelkor\\.io/namespace-role}")
    if got.returncode != 0:
        pytest.skip(got.stderr or f"namespace {ns} missing")
    assert got.stdout.strip() == "agent"
    pods = _kube(
        "get",
        "pods",
        "-l",
        "zelkor.io/workload-type=agent",
        "-o",
        "jsonpath={.items[0].metadata.name}",
        namespace=ns,
    )
    if pods.returncode != 0 or not pods.stdout.strip():
        pytest.skip(f"no agent pod in {ns}")


@pytest.mark.skipif(not os.environ.get("KUBECONFIG"), reason="KUBECONFIG not set")
def test_s28_tcp_from_gptr_pod():
    ns = os.getenv("GPTR_NAMESPACE", "gptr")
    platform_ns = os.getenv("ZELKOR_PLATFORM_NAMESPACE", "zelkor")
    pod = _kube(
        "get",
        "pods",
        "-l",
        "zelkor.io/workload-type=agent",
        "-o",
        "jsonpath={.items[0].metadata.name}",
        namespace=ns,
    ).stdout.strip()
    if not pod:
        pytest.skip("no GPTR agent pod")
    nps = _kube("get", "networkpolicy", "-o", "name", namespace=platform_ns)
    if "agent-egress" not in (nps.stdout or ""):
        pytest.skip("platform NP off")

    def _svc(component: str, port: int, namespace: str) -> tuple[str, int] | None:
        ip = _kube(
            "get",
            "svc",
            "-l",
            f"app.kubernetes.io/component={component}",
            "-o",
            "jsonpath={.items[0].spec.clusterIP}",
            namespace=namespace,
        ).stdout.strip()
        if not ip or ip == "None":
            return None
        return ip, port

    refuse = []
    for component, port, label in (
        ("qdrant", 6333, "qdrant"),
        ("mcp-sandbox-worker", 8081, "worker"),
    ):
        found = _svc(component, port, platform_ns)
        if found:
            refuse.append((found[0], found[1], label))
    refuse.append(("1.1.1.1", 443, "public"))
    allow = []
    for component, port in (("postgresql", 5432), ("valkey", 6379)):
        found = _svc(component, port, platform_ns)
        if found:
            allow.append((found[0], found[1], component))
    if not any(label == "postgresql" for _, _, label in allow):
        ip = _kube(
            "get",
            "svc",
            "-l",
            "cnpg.io/instanceRole=primary",
            "-o",
            "jsonpath={.items[0].spec.clusterIP}",
            namespace=platform_ns,
        ).stdout.strip()
        if ip and ip != "None":
            allow.append((ip, 5432, "postgresql"))

    def _probe(host: str, port: int) -> int:
        script = (
            "import socket,sys\n"
            "s=socket.socket(); s.settimeout(5.0)\n"
            f"err=s.connect_ex(({host!r},{port}))\n"
            "s.close(); sys.stdout.write('ZELKOR_PROBE='+str(err)+'\\n')\n"
        )
        res = _kube("exec", pod, "--", "python", "-c", script, namespace=ns)
        for line in reversed((res.stdout or "").splitlines()):
            if line.startswith("ZELKOR_PROBE="):
                try:
                    return int(line.split("=", 1)[1])
                except ValueError:
                    return 1
        return 1

    bad = [f"{label} {h}:{p}" for h, p, label in refuse if _probe(h, p) == 0]
    assert not bad, f"expected refuse from {pod} to {bad}"
    if allow:
        ok = [f"{label} {h}:{p}" for h, p, label in allow if _probe(h, p) == 0]
        assert ok, f"expected checkpointer allow from {pod} to {allow}"
