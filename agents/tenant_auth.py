import logging
from typing import Any, Dict

from jwt_verifier import resolve_tenant_from_headers, verify_bearer

logger = logging.getLogger("zelkor-tenant-auth")


class TenantAuth:
    """Tenant isolation via RS256/ES256 JWT (JWKS)."""

    async def authenticate(self, headers: Dict[str, str]) -> Dict[str, Any]:
        auth_header = headers.get("authorization") or headers.get("Authorization", "")
        if not auth_header:
            logger.debug("auth denied: no credentials")
            return {
                "identity": "anonymous",
                "tenant_id": None,
                "is_authenticated": False,
            }
        try:
            tenant_id = resolve_tenant_from_headers(headers)
            claims = verify_bearer(auth_header)
            logger.debug(
                "auth ok mode=jwt",
                extra={"event": "auth", "tenant_id": tenant_id},
            )
            return {
                "identity": tenant_id,
                "tenant_id": tenant_id,
                "is_authenticated": True,
                "claims": claims,
                "mode": "jwt",
                "authorization": auth_header,
            }
        except PermissionError as exc:
            logger.warning("JWT verify failed: %s", exc)
            return {
                "identity": "anonymous",
                "tenant_id": None,
                "is_authenticated": False,
                "error": str(exc),
            }
        except Exception as exc:
            logger.warning("JWT verify failed: %s", type(exc).__name__)
            return {
                "identity": "anonymous",
                "tenant_id": None,
                "is_authenticated": False,
                "error": str(exc),
            }


_handler = TenantAuth()


async def authenticate_request(headers: Dict[str, str]) -> Dict[str, Any]:
    return await _handler.authenticate(headers)


try:
    from langgraph_sdk import Auth
except ImportError:
    Auth = None
    auth = _handler
else:
    auth = Auth()

    @auth.authenticate
    async def authenticate(headers: Dict[str, str]) -> Dict[str, Any]:
        result = await _handler.authenticate(headers)
        if not result.get("is_authenticated"):
            raise Exception(result.get("error") or "Authentication required")
        identity = result.get("identity") or result.get("tenant_id")
        out = {
            "identity": identity,
            "tenant_id": result.get("tenant_id") or identity,
            "display_name": identity,
            "permissions": ["read", "write"],
            "is_authenticated": True,
        }
        inbound = result.get("authorization")
        if inbound:
            out["authorization"] = inbound
        return out

    @auth.on.threads.create
    async def on_thread_create(ctx, value):
        if value is None:
            value = {}
        metadata = value.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
            value["metadata"] = metadata
        metadata["tenant_id"] = ctx.user.identity
        return value

    @auth.on.threads
    async def on_threads(ctx, value):
        return {"metadata": {"tenant_id": ctx.user.identity}}
