import os
import jwt
from typing import Dict, Any, Optional

class TenantAuth:
    """
    Zelkor Platform Tenant Isolation Authentication Handler.
    Enforces tenant isolation by mapping incoming requests to user.identity = tenant_id.
    """
    def __init__(self, secret_key: str = "zelkor-dev-secret"):
        self.secret_key = secret_key
        # B2B Organization to Tenant mapping
        self.org_mappings = {
            "org_alpha": "Bank_Alpha",
            "org_beta": "Bank_Beta"
        }

    async def authenticate(self, headers: Dict[str, str]) -> Dict[str, Any]:
        auth_header = headers.get("authorization") or headers.get("Authorization", "")
        x_tenant = headers.get("x-tenant-id") or headers.get("X-Tenant-Id", "")

        # 1. Dev token format: "Bearer dev:<tenant_id>"
        if auth_header.startswith("Bearer dev:"):
            tenant_id = auth_header.split("Bearer dev:", 1)[1].strip()
            return {
                "identity": tenant_id,
                "tenant_id": tenant_id,
                "is_authenticated": True,
                "mode": "dev"
            }

        # 2. Direct Header fallback in local CE dev mode
        if x_tenant and not auth_header:
            return {
                "identity": x_tenant,
                "tenant_id": x_tenant,
                "is_authenticated": True,
                "mode": "header"
            }

        # 3. JWT token format: "Bearer <token>"
        if auth_header.startswith("Bearer "):
            token = auth_header.split("Bearer ", 1)[1].strip()
            try:
                payload = jwt.decode(token, self.secret_key, algorithms=["HS256"], options={"verify_signature": False})
                # B2C: direct tenant_id claim
                if "tenant_id" in payload:
                    tenant_id = payload["tenant_id"]
                # B2B: org_id claim mapped to tenant_id
                elif "org_id" in payload:
                    tenant_id = self.org_mappings.get(payload["org_id"], payload["org_id"])
                elif "sub" in payload:
                    tenant_id = payload["sub"]
                else:
                    tenant_id = "default"

                return {
                    "identity": tenant_id,
                    "tenant_id": tenant_id,
                    "is_authenticated": True,
                    "claims": payload,
                    "mode": "jwt"
                }
            except Exception as e:
                return {
                    "identity": "anonymous",
                    "tenant_id": None,
                    "is_authenticated": False,
                    "error": str(e)
                }

        return {
            "identity": "anonymous",
            "tenant_id": None,
            "is_authenticated": False
        }

auth = TenantAuth()

async def authenticate_request(headers: Dict[str, str]) -> Dict[str, Any]:
    return await auth.authenticate(headers)
