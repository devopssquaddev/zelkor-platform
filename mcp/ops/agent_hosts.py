"""CE-21: write the agent host map — one ConfigMap key per hostname, value = its ClusterIP.

Agent pods run without DNS (`dnsPolicy: None`). They reach the few in-cluster names they call
through `hostAliases`, filled from this map by the MutatingAdmissionPolicy (K8s >= 1.36) or by
`zelkor deploy`. ExternalName Services only work through DNS, so each one is followed to the
ClusterIP of its target. Envoy routes by Host, so every gateway name maps to the same IP.

Runs as a plain Job (not a Helm hook) in the zelkor-mcp image and talks to the API server with
the Job's service-account token. No kubectl.
"""
from __future__ import annotations

import json
import logging
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
from typing import Callable, Optional

logger = logging.getLogger("zelkor-agent-hosts")

SA_DIR = "/var/run/secrets/kubernetes.io/serviceaccount"
CLUSTER_SUFFIX = ".svc.cluster.local"

# get(path) -> dict or None (404); put(path, body) -> None
Getter = Callable[[str], Optional[dict]]
Putter = Callable[[str, dict, str], None]


def _split_external(name: str, default_ns: str) -> tuple[str, str]:
    """`svc.ns.svc.cluster.local` / `svc.ns` / `svc` -> (svc, ns)."""
    host = name.rstrip(".")
    if host.endswith(CLUSTER_SUFFIX):
        host = host[: -len(CLUSTER_SUFFIX)]
    elif host.endswith(".svc"):
        host = host[: -len(".svc")]
    parts = host.split(".")
    return parts[0], (parts[1] if len(parts) > 1 else default_ns)


def resolve_cluster_ip(get: Getter, name: str, namespace: str, *, hops: int = 3) -> Optional[str]:
    """ClusterIP behind a Service, following ExternalName targets inside the cluster."""
    for _ in range(hops + 1):
        svc = get(f"/api/v1/namespaces/{namespace}/services/{name}")
        if not svc:
            return None
        spec = svc.get("spec") or {}
        if spec.get("type") == "ExternalName":
            target = str(spec.get("externalName") or "")
            if not target.rstrip(".").endswith(CLUSTER_SUFFIX):
                return None  # outside the cluster: agents must not reach it directly
            name, namespace = _split_external(target, namespace)
            continue
        ip = str(spec.get("clusterIP") or "")
        return ip if ip and ip != "None" else None
    return None


def build_map(get: Getter, services: list[str], namespace: str) -> dict[str, str]:
    """{short name and FQDN: ClusterIP} for every listed Service that resolves."""
    out: dict[str, str] = {}
    for svc in services:
        ip = resolve_cluster_ip(get, svc, namespace)
        if not ip:
            continue
        out[svc] = ip
        out[f"{svc}.{namespace}{CLUSTER_SUFFIX}"] = ip
    return out


def write_configmap(get: Getter, put: Putter, name: str, namespace: str, data: dict[str, str],
                    release: str) -> None:
    path = f"/api/v1/namespaces/{namespace}/configmaps"
    body = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {
            "name": name,
            "namespace": namespace,
            "labels": {
                "app.kubernetes.io/instance": release,
                "app.kubernetes.io/component": "agent-hosts",
                "zelkor.io/intent": "security.dnsLockdown",
            },
        },
        "data": data,
    }
    if get(f"{path}/{name}") is None:
        put(path, body, "POST")
    else:
        put(f"{path}/{name}", body, "PUT")


def run(get: Getter, put: Putter, *, services: list[str], required: list[str], namespace: str,
        configmap: str, release: str, deadline_s: float, interval_s: float = 5.0,
        sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic) -> int:
    start = clock()
    while True:
        data = build_map(get, services, namespace)
        missing = [s for s in required if s not in data]
        if not missing:
            write_configmap(get, put, configmap, namespace, data, release)
            logger.info("agent host map written", extra={
                "event": "agent_hosts_written", "configmap": configmap, "hostnames": len(data)})
            return 0
        if clock() - start >= deadline_s:
            logger.error("required services never resolved", extra={
                "event": "agent_hosts_failed", "missing": missing})
            return 1
        logger.info("waiting for services", extra={"event": "agent_hosts_wait", "missing": missing})
        sleep(interval_s)


def _api_client() -> tuple[Getter, Putter]:
    host = os.environ.get("KUBERNETES_SERVICE_HOST", "")
    port = os.environ.get("KUBERNETES_SERVICE_PORT", "443")
    base = f"https://{host}:{port}"
    with open(f"{SA_DIR}/token", encoding="utf-8") as fh:
        token = fh.read().strip()
    ctx = ssl.create_default_context(cafile=f"{SA_DIR}/ca.crt")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def get(path: str) -> Optional[dict]:
        req = urllib.request.Request(base + path, headers=headers)
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            raise

    def put(path: str, body: dict, method: str) -> None:
        req = urllib.request.Request(base + path, data=json.dumps(body).encode(), headers=headers,
                                     method=method)
        with urllib.request.urlopen(req, context=ctx, timeout=10):
            pass

    return get, put


def main() -> int:
    from zelkor_logging import configure_logging

    configure_logging("zelkor-agent-hosts")
    services = os.environ.get("AGENT_HOSTS_SERVICES", "").split()
    required = os.environ.get("AGENT_HOSTS_REQUIRED", "").split()
    namespace = os.environ.get("AGENT_HOSTS_NAMESPACE", "")
    configmap = os.environ.get("AGENT_HOSTS_CONFIGMAP", "")
    release = os.environ.get("AGENT_HOSTS_RELEASE", "")
    if not (services and namespace and configmap):
        logger.error("AGENT_HOSTS_SERVICES, AGENT_HOSTS_NAMESPACE and AGENT_HOSTS_CONFIGMAP are required")
        return 2
    get, put = _api_client()
    return run(get, put, services=services, required=required, namespace=namespace,
               configmap=configmap, release=release,
               deadline_s=float(os.environ.get("AGENT_HOSTS_DEADLINE_S", "900")))


if __name__ == "__main__":
    sys.exit(main())
