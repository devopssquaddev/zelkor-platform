"""Extract tenant identity from MCP HTTP request headers.

Identity shortcuts are configuration, not code. Production defaults
(AUTH_DEV_TOKENS_ENABLED / AUTH_TRUST_TENANT_HEADER unset) yield no
tenant from unsigned tokens or headers.
"""
import os
from typing import Dict, Optional


def _flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes", "on")


def extract_tenant(headers: Dict[str, str]) -> Optional[str]:
    auth = headers.get("authorization") or headers.get("Authorization", "")
    x_tenant = headers.get("x-tenant-id") or headers.get("X-Tenant-ID") or headers.get("X-Tenant-Id", "")

    if _flag("AUTH_DEV_TOKENS_ENABLED"):
        prefix = os.getenv("AUTH_DEV_TOKEN_PREFIX", "").strip()
        if prefix:
            bearer = f"Bearer {prefix}"
            if auth.startswith(bearer):
                tenant_id = auth[len(bearer):].strip()
                if tenant_id:
                    return tenant_id

    if _flag("AUTH_TRUST_TENANT_HEADER") and x_tenant:
        return x_tenant.strip()

    return None
