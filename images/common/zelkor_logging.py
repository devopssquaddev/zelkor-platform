"""Shared stdout logging for Zelkor first-party processes.

Honors ZELKOR_LOG_LEVEL and ZELKOR_LOG_FORMAT. See
internal/plan/requirements_platform_logging.md.
"""
from __future__ import annotations

import json
import logging
import os
import sys
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
    return name
