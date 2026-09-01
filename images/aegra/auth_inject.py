"""Guarantee aegra.json / langgraph.json has auth.path so worker images cannot boot no-auth."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger("zelkor-auth-inject")

DEFAULT_AUTH_PATH = "./tenant_auth.py:auth"
_DISCOVER = ("/app/aegra.json", "/app/langgraph.json")


def _discover_config(path: Optional[str] = None) -> Optional[Path]:
    if path:
        candidate = Path(path)
        return candidate if candidate.is_file() else None
    env = (os.getenv("AEGRA_CONFIG") or "").strip()
    if env:
        candidate = Path(env)
        if candidate.is_file():
            return candidate
    for rel in _DISCOVER:
        candidate = Path(rel)
        if candidate.is_file():
            return candidate
    return None


def ensure_auth_config(path: Optional[str] = None) -> Optional[str]:
    config_path = _discover_config(path)
    if config_path is None:
        return None
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return str(config_path)
    if not isinstance(data, dict):
        return str(config_path)
    auth = data.get("auth")
    if isinstance(auth, dict) and auth.get("path"):
        return str(config_path)
    data["auth"] = {"path": DEFAULT_AUTH_PATH}
    dest = Path(os.getenv("AEGRA_AUTH_CONFIG", "/tmp/aegra.with-auth.json"))
    dest.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.environ["AEGRA_CONFIG"] = str(dest)
    logger.info("Mode B wrap: injected auth.path into %s", dest)
    return str(dest)
