import pytest
import jwt
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from agents.tenant_auth import TenantAuth

SECRET_KEY_32 = "zelkor-dev-secret-key-32bytes-min!"

@pytest.mark.asyncio
async def test_dev_token_authentication():
    auth = TenantAuth(secret_key=SECRET_KEY_32)
    headers = {"authorization": "Bearer dev:Bank_Alpha"}
    result = await auth.authenticate(headers)
    assert result["is_authenticated"] is True
    assert result["identity"] == "Bank_Alpha"
    assert result["tenant_id"] == "Bank_Alpha"
    assert result["mode"] == "dev"

@pytest.mark.asyncio
async def test_header_fallback_authentication():
    auth = TenantAuth(secret_key=SECRET_KEY_32)
    headers = {"x-tenant-id": "Bank_Beta"}
    result = await auth.authenticate(headers)
    assert result["is_authenticated"] is True
    assert result["identity"] == "Bank_Beta"
    assert result["tenant_id"] == "Bank_Beta"

@pytest.mark.asyncio
async def test_jwt_b2c_tenant_claim():
    auth = TenantAuth(secret_key=SECRET_KEY_32)
    token = jwt.encode({"tenant_id": "Bank_Alpha", "sub": "user_123"}, SECRET_KEY_32, algorithm="HS256")
    headers = {"authorization": f"Bearer {token}"}
    result = await auth.authenticate(headers)
    assert result["is_authenticated"] is True
    assert result["identity"] == "Bank_Alpha"

@pytest.mark.asyncio
async def test_jwt_b2b_org_mapping():
    auth = TenantAuth(secret_key=SECRET_KEY_32)
    token = jwt.encode({"org_id": "org_beta", "sub": "enterprise_user"}, SECRET_KEY_32, algorithm="HS256")
    headers = {"authorization": f"Bearer {token}"}
    result = await auth.authenticate(headers)
    assert result["is_authenticated"] is True
    assert result["identity"] == "Bank_Beta"

@pytest.mark.asyncio
async def test_unauthenticated_request():
    auth = TenantAuth(secret_key=SECRET_KEY_32)
    headers = {}
    result = await auth.authenticate(headers)
    assert result["is_authenticated"] is False
    assert result["identity"] == "anonymous"
