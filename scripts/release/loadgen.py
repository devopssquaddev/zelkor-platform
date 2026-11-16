#!/usr/bin/env python3
"""CE-19g load generator: fixed-rate /v1/chat/completions through the gateway, counting every
non-2xx response and connection error (open loop: a slow gateway does not lower the rate).

  loadgen.py --url URL --host HOST --key KEY --model M --rps N (--duration S | --until-file F)
             [--retries K] [--out summary.json] [--max-failed N] [--max-ok N]
  loadgen.py --url URL ... --wait-ready SECONDS      (one request at a time until a 2xx)

--max-failed: exit 1 when failed requests exceed N (upgrade gate: 0).
--max-ok: exit 1 when more than N requests succeed (retry storm premise: 100% failures).
A run that sent nothing is never a pass.
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def _attempt(url: str, headers: dict, body: bytes, timeout: float) -> str:
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            r.read()
            return str(r.status)
    except urllib.error.HTTPError as e:
        return str(e.code)
    except (urllib.error.URLError, OSError, TimeoutError):
        return "conn"


def run(*, url: str, host: str, key: str, model: str, rps: float, duration: float = 60.0,
        until_file: Path | None = None, retries: int = 0, timeout: float = 30.0) -> dict:
    headers = {"Content-Type": "application/json"}
    if host:
        headers["Host"] = host
    if key:
        headers["Authorization"] = f"Bearer {key}"
    body = json.dumps({"model": model, "max_tokens": 1,
                       "messages": [{"role": "user", "content": "ping"}]}).encode()
    lock = threading.Lock()
    statuses: Counter = Counter()
    s = {"sent": 0, "attempts": 0, "ok": 0, "non_2xx": 0, "conn_errors": 0}

    def one() -> None:
        final = "conn"
        for _ in range(retries + 1):
            final = _attempt(url, headers, body, timeout)
            with lock:
                s["attempts"] += 1
                statuses[final] += 1
            if final.startswith("2"):
                break
        with lock:
            if final.startswith("2"):
                s["ok"] += 1
            elif final == "conn":
                s["conn_errors"] += 1
            else:
                s["non_2xx"] += 1

    interval = 1.0 / rps
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=max(8, int(rps * timeout * (retries + 1)) + 1)) as pool:
        n = 0
        while True:
            now = time.monotonic()
            if until_file is not None and until_file.exists():
                break
            if now - started >= duration:
                break
            pool.submit(one)
            s["sent"] += 1
            n += 1
            time.sleep(max(0.0, started + n * interval - time.monotonic()))
    s["statuses"] = dict(statuses)
    s["seconds"] = round(time.monotonic() - started, 1)
    s["rps"] = rps
    s["retries"] = retries
    return s


def check(summary: dict, *, max_failed: int | None, max_ok: int | None) -> list[str]:
    reasons = []
    if not summary.get("sent"):
        reasons.append("no requests sent")
    failed = summary.get("non_2xx", 0) + summary.get("conn_errors", 0)
    if max_failed is not None and failed > max_failed:
        reasons.append(f"{failed} failed request(s) > {max_failed} "
                       f"(non_2xx={summary.get('non_2xx', 0)}, conn_errors={summary.get('conn_errors', 0)})")
    if max_ok is not None and summary.get("ok", 0) > max_ok:
        reasons.append(f"{summary['ok']} request(s) succeeded > {max_ok}")
    return reasons


def wait_ready(*, url: str, host: str, key: str, model: str, seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if run(url=url, host=host, key=key, model=model, rps=1, duration=0.5, timeout=10)["ok"]:
            return True
        time.sleep(5)
    return False


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--url", required=True)
    ap.add_argument("--host", default="")
    ap.add_argument("--key", default="")
    ap.add_argument("--model", required=True)
    ap.add_argument("--rps", type=float, default=5)
    ap.add_argument("--duration", type=float, default=60)
    ap.add_argument("--until-file", default="")
    ap.add_argument("--retries", type=int, default=0)
    ap.add_argument("--timeout", type=float, default=30)
    ap.add_argument("--out", default="")
    ap.add_argument("--max-failed", type=int, default=None)
    ap.add_argument("--max-ok", type=int, default=None)
    ap.add_argument("--wait-ready", type=float, default=0)
    args = ap.parse_args(argv)
    if args.wait_ready:
        ok = wait_ready(url=args.url, host=args.host, key=args.key, model=args.model, seconds=args.wait_ready)
        print(f"loadgen: gateway {'ready' if ok else 'not ready'}")
        return 0 if ok else 1
    s = run(url=args.url, host=args.host, key=args.key, model=args.model, rps=args.rps, duration=args.duration,
            until_file=Path(args.until_file) if args.until_file else None, retries=args.retries,
            timeout=args.timeout)
    reasons = check(s, max_failed=args.max_failed, max_ok=args.max_ok)
    s["pass"] = not reasons
    s["reasons"] = reasons
    if args.out:
        Path(args.out).write_text(json.dumps(s, indent=2) + "\n")
    print(json.dumps(s))
    return 1 if reasons else 0


if __name__ == "__main__":
    raise SystemExit(main())
