"""Guarantee aegra.json has auth.path so worker images cannot boot no-auth."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger("zelkor-auth-inject")

DEFAULT_AUTH_PATH = "./tenant_auth.py:auth"


def ensure_auth_config(path: Optional[str] = None) -> Optional[str]:
    config_path = Path(path or os.getenv("AEGRA_CONFIG", "/app/aegra.json"))
    if not config_path.is_file():
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
