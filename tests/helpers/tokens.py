"""Test bearer tokens from ZELKOR_TEST_TOKENS or skip."""
from __future__ import annotations

import json
import os


def test_tokens() -> dict[str, str]:
    raw = os.environ.get("ZELKOR_TEST_TOKENS", "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"ZELKOR_TEST_TOKENS is set but invalid JSON: {exc}") from exc
    if not isinstance(data, dict) or not data:
        raise RuntimeError("ZELKOR_TEST_TOKENS is set but empty or not an object")
    return {str(k): str(v) for k, v in data.items()}


def bearer_for(tenant_key: str = "tenant-a") -> str:
    tokens = test_tokens()
    if tenant_key in tokens:
        return f"Bearer {tokens[tenant_key]}"
    alt = tenant_key.replace("_", "-") if "_" in tenant_key else tenant_key.replace("-", "_")
    if alt in tokens:
        return f"Bearer {tokens[alt]}"
    raise KeyError(tenant_key)
