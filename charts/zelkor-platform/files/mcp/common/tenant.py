"""Extract tenant identity from MCP HTTP request headers."""
from typing import Dict, Optional


def extract_tenant(headers: Dict[str, str]) -> Optional[str]:
    auth = headers.get("authorization") or headers.get("Authorization", "")
    x_tenant = headers.get("x-tenant-id") or headers.get("X-Tenant-ID", "")

    if auth.startswith("Bearer dev:"):
        return auth.split("Bearer dev:", 1)[1].strip()

    if x_tenant:
        return x_tenant.strip()

    if auth.startswith("Bearer "):
        token = auth.split("Bearer ", 1)[1].strip()
        if token and token not in ("dev-key", "zelkor-community-key"):
            return token

    return None
