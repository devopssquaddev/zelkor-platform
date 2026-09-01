"""Round-robin warm pool manager for gVisor sandbox workers."""
import itertools
import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any, Dict, List

logger = logging.getLogger("sandbox-pool")

WORKER_URLS = [u.strip() for u in os.getenv("SANDBOX_WORKER_URLS", "").split(",") if u.strip()]
_cycle = itertools.cycle(WORKER_URLS) if WORKER_URLS else None


def execute_on_worker(code: str, tenant_id: str, timeout: int = 5) -> Dict[str, Any]:
    if not WORKER_URLS:
        raise RuntimeError("No sandbox workers configured")

    last_error = None
    for _ in range(len(WORKER_URLS)):
        worker_url = next(_cycle) if _cycle else WORKER_URLS[0]
        try:
            payload = json.dumps({"code": code, "tenant_id": tenant_id, "timeout": timeout}).encode("utf-8")
            headers = {"Content-Type": "application/json", "X-Tenant-ID": tenant_id}
            token = os.getenv("SANDBOX_WORKER_TOKEN", "").strip()
            if token:
                headers["X-Sandbox-Worker-Token"] = token
            req = urllib.request.Request(
                f"{worker_url.rstrip('/')}/run",
                data=payload,
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout + 2) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            last_error = exc
            logger.warning("Worker %s failed: %s", worker_url, exc)
            continue
    raise RuntimeError(f"All sandbox workers failed: {last_error}")


def workers_healthy() -> bool:
    for url in WORKER_URLS:
        try:
            with urllib.request.urlopen(f"{url.rstrip('/')}/health", timeout=2) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            continue
    return bool(WORKER_URLS)
