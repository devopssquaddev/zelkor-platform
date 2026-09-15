"""Extract tenant identity from MCP HTTP request headers.

Unsigned shortcuts are configuration, not code. Production defaults
(AUTH_DEV_TOKENS_ENABLED / AUTH_TRUST_TENANT_HEADER unset) yield no
tenant from unsigned tokens or headers. When AUTH_JWT_SECRET is set,
inbound Bearer HS256 is verified (same claim order as Aegra TenantAuth).
"""
import json
import os
from typing import Dict, Optional

try:
    import jwt
except ImportError:
    jwt = None


def _flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes", "on")


def _org_mappings() -> dict:
    raw = os.getenv("TENANT_ORG_MAPPINGS", "{}")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _tenant_from_jwt_payload(payload: dict) -> Optional[str]:
    if "tenant_id" in payload and payload["tenant_id"]:
        return str(payload["tenant_id"]).strip() or None
    if "org_id" in payload and payload["org_id"]:
        org_id = str(payload["org_id"])
        mapped = _org_mappings().get(org_id, org_id)
        return str(mapped).strip() or None
    if "sub" in payload and payload["sub"]:
        return str(payload["sub"]).strip() or None
    return "default"


def extract_tenant(headers: Dict[str, str]) -> Optional[str]:
    auth = headers.get("authorization") or headers.get("Authorization", "")
    x_tenant = headers.get("x-tenant-id") or headers.get("X-Tenant-ID") or headers.get("X-Tenant-Id", "")

    secret = os.getenv("AUTH_JWT_SECRET", "").strip()
    if secret and jwt and auth.startswith("Bearer "):
        token = auth.split("Bearer ", 1)[1].strip()
        if token:
            try:
                payload = jwt.decode(token, secret, algorithms=["HS256"])
                tenant_id = _tenant_from_jwt_payload(payload)
                if tenant_id:
                    return tenant_id
            except Exception:
                pass

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
