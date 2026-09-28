"""RS256/ES256 JWT verification against JWKS (shared by MCP backends and Aegra)."""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import urlopen

try:
    import jwt
    from jwt import PyJWK
except ImportError:
    jwt = None
    PyJWK = None

logger = logging.getLogger("zelkor-jwt-verifier")

ALG_BY_KTY = {"RSA": "RS256", "EC": "ES256"}
CLAIM_HEADERS = {
    "tenant_id": "x-tenant-id",
    "org_id": "x-zelkor-claim-org-id",
    "sub": "x-zelkor-claim-sub",
}

_config_error: Optional[str] = None
_jwks_cache: Dict[str, Any] = {}
_jwks_mtime: float = 0.0
_last_kid_reload: float = 0.0


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _audiences() -> List[str]:
    raw = _env("AUTH_JWT_AUDIENCES")
    if not raw:
        return []
    if raw.startswith("["):
        try:
            data = json.loads(raw)
            return [str(x) for x in data if str(x).strip()]
        except json.JSONDecodeError:
            pass
    return [p.strip() for p in raw.split(",") if p.strip()]


def _tenant_claims() -> List[str]:
    raw = _env("AUTH_TENANT_CLAIMS", '["tenant_id","org_id","sub"]')
    if raw.startswith("["):
        try:
            return [str(c).strip() for c in json.loads(raw) if str(c).strip()]
        except json.JSONDecodeError:
            pass
    return [c.strip() for c in raw.split(",") if c.strip()]


def _org_mappings() -> dict:
    raw = _env("TENANT_ORG_MAPPINGS", "{}")
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def validate_startup_config() -> None:
    global _config_error
    issuer = _env("AUTH_JWT_ISSUER")
    aud = _audiences()
    has_jwks = bool(_env("AUTH_JWKS_PATH") or _env("AUTH_JWKS_URI"))
    if not issuer or not aud or not has_jwks:
        _config_error = "AUTH_JWT_ISSUER, AUTH_JWT_AUDIENCES, and JWKS path or URI are required"
        raise RuntimeError(_config_error)
    _config_error = None


def _load_jwks_json() -> dict:
    global _jwks_mtime
    path = _env("AUTH_JWKS_PATH")
    uri = _env("AUTH_JWKS_URI")
    cache_seconds = int(_env("AUTH_JWKS_CACHE_SECONDS", "30"))
    now = time.time()
    if path:
        p = Path(path)
        if p.is_dir():
            jwks_file = p / "jwks"
            if not jwks_file.is_file():
                for child in p.iterdir():
                    if child.suffix == ".json" or child.name == "jwks":
                        jwks_file = child
                        break
        else:
            jwks_file = p
        mtime = jwks_file.stat().st_mtime if jwks_file.is_file() else 0
        if _jwks_cache and mtime <= _jwks_mtime and now - _jwks_mtime < cache_seconds:
            return _jwks_cache
        if not jwks_file.is_file():
            raise PermissionError("JWKS file not found")
        data = json.loads(jwks_file.read_text(encoding="utf-8"))
        _jwks_cache.clear()
        _jwks_cache.update(data)
        _jwks_mtime = mtime
        return data
    if uri:
        if _jwks_cache and now - _jwks_mtime < max(cache_seconds, 300):
            return _jwks_cache
        with urlopen(uri, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        _jwks_cache.clear()
        _jwks_cache.update(data)
        _jwks_mtime = now
        return data
    raise PermissionError("JWKS not configured")


def _key_for_kid(kid: Optional[str]) -> Any:
    if jwt is None or PyJWK is None:
        raise PermissionError("PyJWT not available")
    data = _load_jwks_json()
    keys = data.get("keys") or []
    for entry in keys:
        if entry.get("kty") == "oct":
            continue
        if kid is None or entry.get("kid") == kid:
            kty = entry.get("kty")
            if kty not in ALG_BY_KTY:
                continue
            return PyJWK.from_dict(entry)
    global _last_kid_reload, _jwks_mtime
    now = time.time()
    if now - _last_kid_reload >= 10:
        _last_kid_reload = now
        _jwks_mtime = 0.0
        data = _load_jwks_json()
        for entry in data.get("keys") or []:
            if entry.get("kid") == kid and entry.get("kty") in ALG_BY_KTY:
                return PyJWK.from_dict(entry)
    raise PermissionError("unknown signing key")


def strip_bearer(authz: str) -> str:
    if not authz or not authz.strip():
        raise PermissionError("missing bearer token")
    raw = authz.strip()
    if raw.lower().startswith("bearer "):
        token = raw[7:].strip()
        if not token:
            raise PermissionError("missing bearer token")
        return token
    raise PermissionError("missing bearer token")


def verify_bearer(authz: str) -> dict:
    validate_startup_config()
    token = strip_bearer(authz)
    header = jwt.get_unverified_header(token)
    kid = header.get("kid")
    key = _key_for_kid(kid)
    kty = key._jwk_data.get("kty") if hasattr(key, "_jwk_data") else header.get("kty")
    alg = ALG_BY_KTY.get(kty or "")
    if not alg:
        raise PermissionError("unsupported key type")
    return jwt.decode(
        token,
        key.key,
        algorithms=[alg],
        issuer=_env("AUTH_JWT_ISSUER"),
        audience=_audiences(),
        options={"require": ["exp", "iss", "aud"]},
    )


def tenant_from_claims(claims: dict) -> Optional[str]:
    mappings = _org_mappings()
    for claim in _tenant_claims():
        if claim not in claims or claims[claim] in (None, ""):
            continue
        val = str(claims[claim]).strip()
        if claim == "org_id":
            return str(mappings.get(val, val)).strip() or None
        return val or None
    return None


def resolve_tenant_from_headers(headers: Dict[str, str]) -> str:
    auth = headers.get("authorization") or headers.get("Authorization", "")
    claims = verify_bearer(auth)
    tenant = tenant_from_claims(claims)
    for claim, hdr in CLAIM_HEADERS.items():
        if claim not in _tenant_claims():
            continue
        sent = headers.get(hdr) or headers.get(hdr.upper()) or headers.get(hdr.title())
        if sent is not None and claims.get(claim) is not None and str(sent) != str(claims[claim]):
            logger.warning(
                "identity mismatch on claim %s",
                claim,
                extra={"event": "jwt_claim_mismatch"},
            )
            raise PermissionError("identity mismatch")
    if not tenant:
        raise PermissionError("no tenant claim")
    return tenant
