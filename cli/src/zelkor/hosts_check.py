"""CE-21 `zelkor verify <platform> --hosts`: agent pods without DNS still reach what they need.

Checks, each printed as PASS / FAIL / WARN:
  1. every host-map entry still points at the live ClusterIP (ExternalName followed);
  2. every running locked pod of this platform (agents, platform Aegra) carries exactly the map's entries;
  3. every HTTP API an agent's sidecar relays to exists on the platform (no stale route names);
  4. agents left with DNS (lockdown inactive) are reported.
"""
from __future__ import annotations

import json
import logging
import sys
from typing import Any, Callable, Optional

logger = logging.getLogger("zelkor-cli")

RunFn = Callable[..., Any]
CLUSTER_SUFFIX = ".svc.cluster.local"


def _json(runner: RunFn, argv: list[str]) -> Optional[dict]:
    res = runner(argv, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        return None
    try:
        return json.loads(res.stdout or "{}")
    except json.JSONDecodeError:
        return None


def _service_ip(runner: RunFn, kubectl: list[str], name: str, namespace: str, hops: int = 3) -> str:
    for _ in range(hops + 1):
        svc = _json(runner, kubectl + ["get", "svc", name, "-n", namespace, "-o", "json"])
        if not svc:
            return ""
        spec = svc.get("spec") or {}
        if spec.get("type") == "ExternalName":
            target = str(spec.get("externalName") or "").rstrip(".")
            if not target.endswith(CLUSTER_SUFFIX):
                return ""
            parts = target[: -len(CLUSTER_SUFFIX)].split(".")
            name, namespace = parts[0], (parts[1] if len(parts) > 1 else namespace)
            continue
        ip = str(spec.get("clusterIP") or "")
        return "" if ip == "None" else ip
    return ""


def _short(host: str, namespace: str) -> str:
    suffix = f".{namespace}{CLUSTER_SUFFIX}"
    return host[: -len(suffix)] if host.endswith(suffix) else host


def _pod_aliases(pod: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for entry in ((pod.get("spec") or {}).get("hostAliases") or []):
        for host in entry.get("hostnames") or []:
            out[str(host)] = str(entry.get("ip") or "")
    return out


def _api_upstreams(pod: dict) -> list[str]:
    names: list[str] = []
    for container in ((pod.get("spec") or {}).get("containers") or []):
        for env in container.get("env") or []:
            if env.get("name") == "ZELKOR_API_UPSTREAMS":
                for item in str(env.get("value") or "").split(","):
                    if "=" in item:
                        names.append(item.split("=", 1)[0].strip())
    return names


def check_agent_hosts(release: str, namespace: str, *, kubectl: list[str], runner: RunFn,
                      contract_configmap: str = "zelkor-platform-contract") -> int:
    contract = _json(runner, kubectl + ["get", "configmap", contract_configmap, "-n", namespace, "-o", "json"])
    contract_data = (contract or {}).get("data") or {}
    cm_name = contract_data.get("AGENT_HOSTS_CONFIGMAP", "")
    if not cm_name:
        print(f"SKIP hosts       {namespace}/{release} publishes no AGENT_HOSTS_CONFIGMAP (lockdown off or platform predates CE-21)")
        return 0
    cm = _json(runner, kubectl + ["get", "configmap", cm_name, "-n", namespace, "-o", "json"])
    host_map: dict[str, str] = {str(k): str(v) for k, v in ((cm or {}).get("data") or {}).items()}
    failed = 0
    if not host_map:
        print(f"FAIL host map    {cm_name} missing or empty; check job/{release}-agent-hosts-<revision>")
        return 1

    for host in sorted(h for h in host_map if not h.endswith(CLUSTER_SUFFIX)):
        live = _service_ip(runner, kubectl, host, namespace)
        ok = live == host_map[host]
        failed += 0 if ok else 1
        print(f"{'PASS' if ok else 'FAIL'} host map    {host} -> {host_map[host]}"
              + ("" if ok else f" (live: {live or 'missing'}; upgrade the platform to rewrite the map)"))

    apis = {n.strip() for n in contract_data.get("HTTP_APIS", "").split(",") if n.strip()}
    # Agents (any namespace) and this platform's own Aegra; anything else is not ours to judge.
    pods = _json(runner, kubectl + ["get", "pods", "-A", "-o", "json"]) or {}
    for pod in pods.get("items") or []:
        meta = pod.get("metadata") or {}
        where = f"{meta.get('namespace')}/{meta.get('name')}"
        labels = meta.get("labels") or {}
        is_agent = labels.get("zelkor.io/workload-type") == "agent"
        is_platform_aegra = (meta.get("namespace") == namespace
                             and labels.get("app.kubernetes.io/instance") == release
                             and labels.get("app.kubernetes.io/component") == "aegra")
        if not (is_agent or is_platform_aegra):
            continue
        if labels.get("zelkor.io/platform-release", release) != release:
            continue
        if (meta.get("annotations") or {}).get("zelkor.io/dns-lockdown") == "inactive":
            print(f"WARN dns         {where} keeps DNS (lockdown inactive); redeploy with `zelkor deploy`")
        elif labels.get("zelkor.io/dns-lockdown") == "on":
            have = {_short(h, namespace): ip for h, ip in _pod_aliases(pod).items()}
            want = {_short(h, namespace): ip for h, ip in host_map.items()}
            drift = sorted(h for h in set(have) | set(want) if have.get(h) != want.get(h))
            failed += 1 if drift else 0
            print(f"{'FAIL' if drift else 'PASS'} pod hosts   {where}"
                  + (f" differs on {', '.join(drift)}; delete the pod (K8s >= 1.36) or run `zelkor deploy`" if drift else ""))
        for name in _api_upstreams(pod):
            ok = name in apis
            failed += 0 if ok else 1
            print(f"{'PASS' if ok else 'FAIL'} http api    {where} -> {release}-api-{name}"
                  + ("" if ok else " has no route on the platform; redeploy the agent or add the API"))
    logger.info("verify hosts release=%s failed=%s", release, failed)
    print(f"{'FAILED' if failed else 'OK'}: {failed} problem(s) in the agent host checks for {namespace}/{release}",
          file=sys.stderr if failed else sys.stdout)
    return 1 if failed else 0
