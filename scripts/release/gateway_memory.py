#!/usr/bin/env python3
"""CE-19g: Envoy dataplane memory under a retry storm, from the kubelet summary API.

  gateway_memory.py sample --context CTX [--namespace envoy-gateway-system] >> samples.csv
  gateway_memory.py analyze --samples samples.csv --thresholds gate-thresholds.json [--out FILE]

sample appends `epoch,pod,container,working_set_bytes` for every container of every Envoy Gateway
proxy pod (no metrics-server needed). analyze gates the configured container: every sample under
envoy_memory_ceiling_mib, and the mean of the last window within max_growth_pct of the first
window after warmup ("flat"). Too few samples is a failure, not a pass.
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

PROXY_SELECTOR = "app.kubernetes.io/component=proxy,app.kubernetes.io/managed-by=envoy-gateway"
MIB = 2**20


@dataclass(frozen=True)
class Sample:
    t: float
    pod: str
    container: str
    bytes: int


def working_sets(summary: dict, *, namespace: str, pods: set[str]) -> dict[tuple[str, str], int]:
    out = {}
    for pod in summary.get("pods") or []:
        ref = pod.get("podRef") or {}
        if ref.get("namespace") != namespace or ref.get("name") not in pods:
            continue
        for c in pod.get("containers") or []:
            ws = ((c.get("memory") or {}).get("workingSetBytes"))
            if ws is not None:
                out[(ref["name"], c.get("name", ""))] = int(ws)
    return out


def _kubectl(context: str, *args: str) -> dict:
    r = subprocess.run(["kubectl", "--context", context, *args], capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def sample(context: str, namespace: str) -> list[Sample]:
    pods = _kubectl(context, "-n", namespace, "get", "pods", "-l", PROXY_SELECTOR, "-o", "json")["items"]
    by_node: dict[str, set[str]] = {}
    for p in pods:
        node = (p.get("spec") or {}).get("nodeName")
        if node:
            by_node.setdefault(node, set()).add(p["metadata"]["name"])
    now = time.time()
    out = []
    for node, names in by_node.items():
        summary = _kubectl(context, "get", "--raw", f"/api/v1/nodes/{node}/proxy/stats/summary")
        for (pod, container), ws in working_sets(summary, namespace=namespace, pods=names).items():
            out.append(Sample(now, pod, container, ws))
    return out


def _mean(xs: list[int]) -> float:
    return sum(xs) / len(xs)


def analyze(samples: list[Sample], gate: dict) -> tuple[bool, dict]:
    container = gate["container"]
    ceiling = gate["envoy_memory_ceiling_mib"] * MIB
    series = [s for s in samples if s.container == container]
    report: dict = {"container": container, "ceiling_mib": gate["envoy_memory_ceiling_mib"],
                    "max_growth_pct": gate["max_growth_pct"], "samples": len(series)}
    if not series:
        report["reason"] = "no samples for the gated container"
        return False, report
    t0 = min(s.t for s in series)
    report["max_mib"] = round(max(s.bytes for s in series) / MIB, 1)
    over = [s for s in series if s.bytes > ceiling]
    if over:
        report["reason"] = f"{len(over)} sample(s) over the {gate['envoy_memory_ceiling_mib']} MiB ceiling"
        return False, report
    worst = 0.0
    for pod in sorted({s.pod for s in series}):
        pts = sorted((s for s in series if s.pod == pod), key=lambda s: s.t)
        start = t0 + gate["warmup_seconds"]
        end = pts[-1].t
        first = [s.bytes for s in pts if start <= s.t < start + gate["window_seconds"]]
        last = [s.bytes for s in pts if s.t > end - gate["window_seconds"]]
        if len(first) < 2 or len(last) < 2 or end - start < 2 * gate["window_seconds"]:
            report["reason"] = f"too few samples for {pod} to judge growth"
            return False, report
        growth = (_mean(last) - _mean(first)) / _mean(first) * 100
        worst = max(worst, growth)
    report["growth_pct"] = round(worst, 1)
    if worst > gate["max_growth_pct"]:
        report["reason"] = f"memory growth {worst:.1f}% > {gate['max_growth_pct']}%"
        return False, report
    report["reason"] = ""
    return True, report


def _read(path: Path) -> list[Sample]:
    with path.open(newline="") as f:
        return [Sample(float(r[0]), r[1], r[2], int(r[3])) for r in csv.reader(f) if r]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sample")
    s.add_argument("--context", required=True)
    s.add_argument("--namespace", default="envoy-gateway-system")
    a = sub.add_parser("analyze")
    a.add_argument("--samples", required=True)
    a.add_argument("--thresholds", required=True)
    a.add_argument("--out", default="")
    args = ap.parse_args(argv)
    if args.cmd == "sample":
        w = csv.writer(sys.stdout)
        for x in sample(args.context, args.namespace):
            w.writerow([f"{x.t:.0f}", x.pod, x.container, x.bytes])
        return 0
    gate = json.loads(Path(args.thresholds).read_text())["retry_storm"]
    ok, report = analyze(_read(Path(args.samples)), gate)
    report["pass"] = ok
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
