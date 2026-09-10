"""Shared stdout logging for Zelkor first-party processes.

Honors ZELKOR_LOG_LEVEL and ZELKOR_LOG_FORMAT. See
internal/plan/requirements_platform_logging.md.
"""
from __future__ import annotations

import atexit
import json
import logging
import os
import signal
import sys
import threading
from datetime import datetime, timezone
from typing import Optional

_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "WARN": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}

_CONTEXT_KEYS = ("tenant_id", "graph_id", "run_id", "request_id", "trace_id", "event")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "component": getattr(record, "component", record.name),
        }
        for key in _CONTEXT_KEYS:
            val = getattr(record, key, None)
            if val:
                payload[key] = val
        sandbox = getattr(record, "sandbox", None)
        if isinstance(sandbox, dict) and sandbox:
            payload["sandbox"] = sandbox
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


class _ComponentFilter(logging.Filter):
    def __init__(self, component: str) -> None:
        super().__init__()
        self.component = component

    def filter(self, record: logging.LogRecord) -> bool:
        if not getattr(record, "component", None):
            record.component = self.component
        return True


def parse_level(raw: Optional[str] = None) -> int:
    name = (raw if raw is not None else os.getenv("ZELKOR_LOG_LEVEL", "INFO")).strip().upper()
    return _LEVELS.get(name, logging.INFO)


def parse_format(raw: Optional[str] = None) -> str:
    name = (raw if raw is not None else os.getenv("ZELKOR_LOG_FORMAT", "json")).strip().lower()
    if name in ("json", "text"):
        return name
    return "json"


def _component_name() -> str:
    return str(getattr(configure_logging, "_component", None) or os.getenv("ZELKOR_LOG_COMPONENT", "") or "zelkor")


def _lifecycle_enabled() -> bool:
    return os.getenv("ZELKOR_LOG_LIFECYCLE", "1").strip().lower() not in ("0", "false", "off")


def log_startup(*, message: str = "starting") -> None:
    name = _component_name()
    logging.getLogger(name).info(message, extra={"event": "startup", "component": name})


def log_shutdown(*, message: str = "stopping") -> None:
    if getattr(log_shutdown, "_done", False):
        return
    log_shutdown._done = True  # type: ignore[attr-defined]
    try:
        name = _component_name()
        logging.getLogger(name).info(message, extra={"event": "shutdown", "component": name})
        for handler in logging.getLogger().handlers:
            handler.flush()
    except Exception:
        pass


def _on_signal(signum: int, _frame: object) -> None:
    log_shutdown()
    signal.signal(signum, signal.SIG_DFL)
    os.kill(os.getpid(), signum)


def install_lifecycle_hooks() -> None:
    """INFO shutdown on atexit and SIGTERM/SIGINT. Idempotent. Skip under pytest."""
    if getattr(install_lifecycle_hooks, "_done", False):
        return
    if os.getenv("PYTEST_CURRENT_TEST"):
        return
    if not _lifecycle_enabled():
        return
    install_lifecycle_hooks._done = True  # type: ignore[attr-defined]
    atexit.register(log_shutdown)
    if threading.current_thread() is not threading.main_thread():
        return
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _on_signal)
        except (ValueError, OSError):
            pass


def configure_logging(component: Optional[str] = None, *, force: bool = False) -> str:
    """Configure the root logger. Returns the component name used."""
    if getattr(configure_logging, "_done", False) and not force:
        return getattr(configure_logging, "_component", component or "zelkor")

    name = (
        (component or "").strip()
        or os.getenv("ZELKOR_LOG_COMPONENT", "").strip()
        or "zelkor"
    )
    level = parse_level()
    fmt = parse_format()

    handler = logging.StreamHandler(sys.stdout)
    if fmt == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )
    handler.addFilter(_ComponentFilter(name))

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)

    configure_logging._done = True  # type: ignore[attr-defined]
    configure_logging._component = name  # type: ignore[attr-defined]
    if force:
        log_shutdown._done = False  # type: ignore[attr-defined]
    log_startup()
    install_lifecycle_hooks()
    return name
