"""Extract tenant identity from verified JWT on MCP tool calls."""
from typing import Dict, Optional

import jwt

from common.jwt_verifier import resolve_tenant_from_headers

_MAX_KEY_LEN = 1024


def extract_tenant(headers: Dict[str, str]) -> Optional[str]:
    try:
        return resolve_tenant_from_headers(headers)
    except (PermissionError, jwt.PyJWTError):
        return None


def _reject_tenant(tenant: str) -> str:
    if not isinstance(tenant, str) or not tenant or tenant.strip() != tenant:
        raise PermissionError("invalid tenant")
    if "/" in tenant or "\\" in tenant or ".." in tenant:
        raise PermissionError("invalid tenant")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in tenant):
        raise PermissionError("invalid tenant")
    return tenant


def normalize_key(raw: str) -> str:
    """Reject empty, '..', absolute, backslash, NUL/control, and over-long keys.

    Duplicate separators collapse. The result never starts with '/' and never
    contains an empty or '..' segment.
    """
    if not isinstance(raw, str):
        raise PermissionError("key must be a string")
    if raw == "" or len(raw) > _MAX_KEY_LEN:
        raise PermissionError("empty or over-long key")
    if "\\" in raw or "\x00" in raw:
        raise PermissionError("key contains a forbidden character")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in raw):
        raise PermissionError("key contains a control character")
    if raw.startswith("/"):
        raise PermissionError("absolute key")
    parts = []
    for segment in raw.split("/"):
        if segment == "":
            continue
        if segment == "..":
            raise PermissionError("key contains '..'")
        parts.append(segment)
    if not parts:
        raise PermissionError("empty key")
    normalized = "/".join(parts)
    if len(normalized) > _MAX_KEY_LEN:
        raise PermissionError("over-long key")
    return normalized


def tenant_key(tenant: str, raw: str) -> str:
    """Prefix a normalized object key with the verified tenant."""
    safe = _reject_tenant(tenant)
    return f"{safe}/{normalize_key(raw)}"


def strip_tenant(tenant: str, s3_key: str) -> str:
    """Drop the tenant prefix. Refuse keys that are not under that prefix."""
    safe = _reject_tenant(tenant)
    prefix = f"{safe}/"
    if not isinstance(s3_key, str) or not s3_key.startswith(prefix):
        raise PermissionError("key is outside the tenant prefix")
    rest = s3_key[len(prefix):]
    if not rest or rest.startswith("/") or ".." in rest.split("/"):
        raise PermissionError("key is outside the tenant prefix")
    if "\\" in rest or any(ord(ch) < 32 or ord(ch) == 127 for ch in rest):
        raise PermissionError("key is outside the tenant prefix")
    return rest
