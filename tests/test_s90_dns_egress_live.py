"""S-90 (P8, P18; fail-closed `egress-dns`): an agent pod cannot send data out through DNS.

Before CE-21 an agent could resolve any name through kube-dns, so data written into a query
label reached the attacker's authoritative nameserver although every direct connection was
blocked. Proof 2026-11-18 on demohetzner: a never-seen `<random>.example.com` came back with
example.com's SOA from ns.cloudflare.com.

Live (L3): for every locked agent pod (zelkor.io/dns-lockdown=on) the probe runs in its sidecar:
A and TXT lookups of a never-seen outside name and of github.com must fail, kube-dns must be
unreachable on UDP and TCP 53, and no answer may carry an outside SOA. Positive control: the
gateway is still reachable by name from /etc/hosts.
"""
from __future__ import annotations

import json
import os
import subprocess

import pytest

from tests.helpers.kube import kubectl_cmd

PROBE = r"""
import json, os, random, socket, struct

def dns(name, qtype, server, tcp=False):
    tid = random.randint(0, 0xFFFF)
    q = struct.pack(">HHHHHH", tid, 0x0100, 1, 0, 0, 0)
    q += b"".join(bytes([len(p)]) + p.encode() for p in name.split(".")) + b"\0" + struct.pack(">HH", qtype, 1)
    try:
        if tcp:
            s = socket.create_connection((server, 53), 3)
            s.sendall(struct.pack(">H", len(q)) + q)
            r = s.recv(4096)[2:]
        else:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(3)
            s.sendto(q, (server, 53))
            r, _ = s.recvfrom(4096)
    except Exception as e:
        return {"answered": False, "error": type(e).__name__}
    an, ns = struct.unpack(">HH", r[6:10])
    return {"answered": True, "rcode": r[3] & 0xF, "answers": an, "authority": ns}

def resolves(name):
    try:
        socket.getaddrinfo(name, 443)
        return True
    except OSError:
        return False

kube_dns = os.environ.get("S90_KUBE_DNS", "10.96.0.10")
tag = "zelkor-s90-" + os.urandom(4).hex() + ".example.com"
out = {
    "random_resolves": resolves(tag),
    "github_resolves": resolves("github.com"),
    "udp_a": dns(tag, 1, kube_dns),
    "udp_txt": dns("example.com", 16, kube_dns),
    "tcp_a": dns(tag, 1, kube_dns, tcp=True),
    "gateway": resolves(os.environ.get("S90_GATEWAY_HOST", "")),
}
print("S90 " + json.dumps(out))
"""


def _kubectl_json(*args: str):
    res = subprocess.run(kubectl_cmd(*args, "-o", "json"), capture_output=True, text=True, timeout=60)
    if res.returncode != 0:
        pytest.skip(f"kubectl failed: {res.stderr.strip()[:200]}")
    return json.loads(res.stdout or "{}")


def _kube_dns_ip() -> str:
    svc = _kubectl_json("get", "svc", "kube-dns", "-n", "kube-system")
    return str((svc.get("spec") or {}).get("clusterIP") or "")


def _locked_pods() -> list[dict]:
    pods = _kubectl_json("get", "pods", "-A", "-l", "zelkor.io/dns-lockdown=on")
    return [p for p in pods.get("items") or [] if (p.get("status") or {}).get("phase") == "Running"]


def _gateway_host(pod: dict) -> str:
    """Gateway host the pod calls: sidecar runtimes set ZELKOR_LLM_UPSTREAM, Aegra agents OPENAI_BASE_URL."""
    env = {e.get("name"): str(e.get("value") or "") for c in pod["spec"]["containers"] for e in c.get("env") or []}
    for key in ("ZELKOR_LLM_UPSTREAM", "OPENAI_BASE_URL", "MCP_URL"):
        url = env.get(key, "")
        if "//" in url:
            return url.split("//", 1)[1].split("/", 1)[0].split(":", 1)[0]
    return ""


def test_s90_locked_agents_cannot_resolve_or_reach_dns():
    if not os.environ.get("KUBECONTEXT", "").strip():
        pytest.skip("KUBECONTEXT not set")
    pods = _locked_pods()
    if not pods:
        pytest.skip("no running agent pod with zelkor.io/dns-lockdown=on (deploy one with zelkor deploy)")
    kube_dns = _kube_dns_ip()
    for pod in pods:
        meta = pod["metadata"]
        container = "sidecar" if any(c["name"] == "sidecar" for c in pod["spec"]["containers"]) else \
            pod["spec"]["containers"][0]["name"]
        where = f"{meta['namespace']}/{meta['name']}"
        res = subprocess.run(
            kubectl_cmd("exec", "-i", "-n", meta["namespace"], meta["name"], "-c", container, "--",
                        "env", f"S90_KUBE_DNS={kube_dns}", f"S90_GATEWAY_HOST={_gateway_host(pod)}",
                        "python", "-"),
            input=PROBE, capture_output=True, text=True, timeout=120)
        line = next((ln for ln in res.stdout.splitlines() if ln.startswith("S90 ")), "")
        assert line, f"{where}: probe did not run: {res.stderr[-300:]}"
        out = json.loads(line[4:])
        assert pod["spec"].get("dnsPolicy") == "None", f"{where}: dnsPolicy {pod['spec'].get('dnsPolicy')}"
        assert not out["random_resolves"] and not out["github_resolves"], f"{where}: outside names resolve: {out}"
        for key in ("udp_a", "udp_txt", "tcp_a"):
            assert not out[key]["answered"], f"{where}: kube-dns answered {key}: {out[key]}"
        host = _gateway_host(pod)
        assert host, f"{where}: no gateway URL in the pod env; the positive control cannot run"
        assert out["gateway"], f"{where}: positive control failed, {host} does not resolve from /etc/hosts"
