"""Round-robin warm pool manager for gVisor sandbox workers."""
import errno
import itertools
import json
import logging
import os
import socket
import urllib.error
import urllib.request
from typing import Any, Dict

from sandbox.execution_report import log_sandbox_execution, report_from_worker_result

logger = logging.getLogger("zelkor-mcp-sandbox")

WORKER_URLS = [u.strip() for u in os.getenv("SANDBOX_WORKER_URLS", "").split(",") if u.strip()]
_cycle = itertools.cycle(WORKER_URLS) if WORKER_URLS else None

_CONNECT_ERRNOS = {
    errno.ECONNREFUSED,
    errno.ENETUNREACH,
    errno.EHOSTUNREACH,
}
for _name in ("EAI_AGAIN", "EAI_NONAME", "EAI_FAIL"):
    _val = getattr(errno, _name, None)
    if _val is not None:
        _CONNECT_ERRNOS.add(_val)


def _is_pre_send_connect_error(exc: BaseException) -> bool:
    """Retry only when the HTTP request never left the client."""
    if isinstance(exc, urllib.error.HTTPError):
        return False
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return False
    reason: BaseException = getattr(exc, "reason", exc)
    if isinstance(reason, (TimeoutError, socket.timeout)):
        return False
    if isinstance(reason, ConnectionRefusedError):
        return True
    if isinstance(reason, socket.gaierror):
        return True
    if isinstance(reason, OSError):
        return getattr(reason, "errno", None) in _CONNECT_ERRNOS
    return False


def execute_on_worker(code: str, tenant_id: str, timeout: int = 5) -> Dict[str, Any]:
    if not WORKER_URLS:
        raise RuntimeError("No sandbox workers configured")

    last_error = None
    for _ in range(len(WORKER_URLS)):
        worker_url = next(_cycle) if _cycle else WORKER_URLS[0]
        try:
            # tenant_id in body only — set by sandbox MCP from verified JWT; not a client header.
            payload = json.dumps({"code": code, "tenant_id": tenant_id, "timeout": timeout}).encode("utf-8")
            headers = {"Content-Type": "application/json"}
            token = os.getenv("SANDBOX_WORKER_TOKEN", "").strip()
            if token:
                headers["X-Sandbox-Worker-Token"] = token
            req = urllib.request.Request(
                f"{worker_url.rstrip('/')}/run",
                data=payload,
                headers=headers,
                method="POST",
            )
            logger.debug(
                "dispatch sandbox execute timeout=%s",
                timeout,
                extra={"event": "sandbox_execute", "tenant_id": tenant_id},
            )
            with urllib.request.urlopen(req, timeout=timeout + 2) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            report = report_from_worker_result(code, result)
            if not result.get("execution"):
                result["execution"] = report.to_execution_dict()
            log_sandbox_execution(
                logger,
                report,
                tenant_id=tenant_id,
                worker_url=worker_url,
            )
            return result
        except Exception as exc:
            last_error = exc
            if not _is_pre_send_connect_error(exc):
                logger.warning("Worker %s failed (no retry): %s", worker_url, exc)
                raise
            logger.warning("Worker %s connect failed, trying next: %s", worker_url, exc)
            continue
    raise RuntimeError(f"All sandbox workers failed: {last_error}")


def workers_healthy() -> bool:
    if not WORKER_URLS:
        return False
    for url in WORKER_URLS:
        try:
            with urllib.request.urlopen(f"{url.rstrip('/')}/health", timeout=2) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            continue
    logger.warning(
        "all sandbox worker health probes failed",
        extra={"event": "sandbox_health", "worker_count": len(WORKER_URLS)},
    )
    return False
