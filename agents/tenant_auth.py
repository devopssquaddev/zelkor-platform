import json
import logging
import os
try:
    import jwt
except ImportError:
    jwt = None
from typing import Dict, Any

logger = logging.getLogger("zelkor-tenant-auth")


def _flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes", "on")


class TenantAuth:
    """
    Zelkor Platform Tenant Isolation Authentication Handler.
    Enforces tenant isolation by mapping incoming requests to user.identity = tenant_id.

    Unsigned local shortcuts (token prefix, tenant header) are off unless
    AUTH_DEV_TOKENS_ENABLED / AUTH_TRUST_TENANT_HEADER are set.
    JWT HS256 is verified when AUTH_JWT_SECRET is set. Unsigned JWT is rejected.
    """
    def __init__(self, secret_key: str = ""):
        self.secret_key = secret_key or os.getenv("AUTH_JWT_SECRET", "")
        raw_mappings = os.getenv("TENANT_ORG_MAPPINGS", "{}")
        try:
            self.org_mappings = json.loads(raw_mappings)
        except json.JSONDecodeError:
            self.org_mappings = {}
        self.dev_tokens_enabled = _flag("AUTH_DEV_TOKENS_ENABLED")
        self.dev_token_prefix = os.getenv("AUTH_DEV_TOKEN_PREFIX", "").strip()
        self.trust_tenant_header = _flag("AUTH_TRUST_TENANT_HEADER")

    async def authenticate(self, headers: Dict[str, str]) -> Dict[str, Any]:
        auth_header = headers.get("authorization") or headers.get("Authorization", "")
        x_tenant = headers.get("x-tenant-id") or headers.get("X-Tenant-Id") or headers.get("X-Tenant-ID", "")

        if self.dev_tokens_enabled and self.dev_token_prefix:
            bearer = f"Bearer {self.dev_token_prefix}"
            if auth_header.startswith(bearer):
                tenant_id = auth_header[len(bearer):].strip()
                if tenant_id:
                    logger.debug(
                        "auth ok mode=dev",
                        extra={"event": "auth", "tenant_id": tenant_id},
                    )
                    return {
                        "identity": tenant_id,
                        "tenant_id": tenant_id,
                        "is_authenticated": True,
                        "mode": "dev"
                    }

        if self.trust_tenant_header and x_tenant and not auth_header:
            tenant_id = x_tenant.strip()
            logger.debug(
                "auth ok mode=header",
                extra={"event": "auth", "tenant_id": tenant_id},
            )
            return {
                "identity": tenant_id,
                "tenant_id": tenant_id,
                "is_authenticated": True,
                "mode": "header"
            }

        if auth_header.startswith("Bearer "):
            token = auth_header.split("Bearer ", 1)[1].strip()
            if not jwt:
                logger.error("PyJWT not installed")
                return {
                    "is_authenticated": False,
                    "identity": None,
                    "tenant_id": None,
                    "error": "PyJWT not installed"
                }
            if not self.secret_key:
                logger.error("AUTH_JWT_SECRET is required to verify Bearer JWT")
                return {
                    "is_authenticated": False,
                    "identity": "anonymous",
                    "tenant_id": None,
                    "error": "AUTH_JWT_SECRET is required to verify Bearer JWT",
                }
            try:
                payload = jwt.decode(token, self.secret_key, algorithms=["HS256"])
                if "tenant_id" in payload:
                    tenant_id = payload["tenant_id"]
                elif "org_id" in payload:
                    tenant_id = self.org_mappings.get(payload["org_id"], payload["org_id"])
                elif "sub" in payload:
                    tenant_id = payload["sub"]
                else:
                    tenant_id = "default"

                logger.debug(
                    "auth ok mode=jwt",
                    extra={"event": "auth", "tenant_id": tenant_id},
                )
                return {
                    "identity": tenant_id,
                    "tenant_id": tenant_id,
                    "is_authenticated": True,
                    "claims": payload,
                    "mode": "jwt"
                }
            except Exception as e:
                logger.warning("JWT verify failed: %s", type(e).__name__)
                return {
                    "identity": "anonymous",
                    "tenant_id": None,
                    "is_authenticated": False,
                    "error": str(e)
                }

        logger.debug("auth denied: no credentials")
        return {
            "identity": "anonymous",
            "tenant_id": None,
            "is_authenticated": False
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
        return {
            "identity": identity,
            "tenant_id": result.get("tenant_id") or identity,
            "display_name": identity,
            "permissions": ["read", "write"],
            "is_authenticated": True,
        }

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
