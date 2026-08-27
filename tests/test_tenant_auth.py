import pytest
import asyncio
try:
    import jwt
except ImportError:
    jwt = None
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from agents.tenant_auth import TenantAuth

SECRET_KEY_32 = "zelkor-dev-secret-key-32bytes-min!"


@pytest.fixture
def local_auth_env(monkeypatch):
    monkeypatch.setenv("AUTH_DEV_TOKENS_ENABLED", "true")
    monkeypatch.setenv("AUTH_DEV_TOKEN_PREFIX", "dev:")
    monkeypatch.setenv("AUTH_TRUST_TENANT_HEADER", "true")


def test_dev_token_authentication(local_auth_env):
    auth = TenantAuth(secret_key=SECRET_KEY_32)
    headers = {"authorization": "Bearer dev:tenant_a"}
    result = asyncio.run(auth.authenticate(headers))
    assert result["is_authenticated"] is True
    assert result["identity"] == "tenant_a"
    assert result["tenant_id"] == "tenant_a"
    assert result["mode"] == "dev"


def test_dev_token_disabled_by_default(monkeypatch):
    monkeypatch.delenv("AUTH_DEV_TOKENS_ENABLED", raising=False)
    monkeypatch.delenv("AUTH_DEV_TOKEN_PREFIX", raising=False)
    auth = TenantAuth(secret_key=SECRET_KEY_32)
    headers = {"authorization": "Bearer dev:tenant_a"}
    result = asyncio.run(auth.authenticate(headers))
    assert result["is_authenticated"] is False


def test_header_fallback_authentication(local_auth_env):
    auth = TenantAuth(secret_key=SECRET_KEY_32)
    headers = {"x-tenant-id": "tenant_b"}
    result = asyncio.run(auth.authenticate(headers))
    assert result["is_authenticated"] is True
    assert result["identity"] == "tenant_b"
    assert result["tenant_id"] == "tenant_b"


def test_header_fallback_disabled_by_default(monkeypatch):
    monkeypatch.delenv("AUTH_TRUST_TENANT_HEADER", raising=False)
    auth = TenantAuth(secret_key=SECRET_KEY_32)
    headers = {"x-tenant-id": "tenant_b"}
    result = asyncio.run(auth.authenticate(headers))
    assert result["is_authenticated"] is False


def test_jwt_b2c_tenant_claim():
    if not jwt:
        pytest.skip("PyJWT not installed")
    auth = TenantAuth(secret_key=SECRET_KEY_32)
    token = jwt.encode({"tenant_id": "tenant_a", "sub": "user_123"}, SECRET_KEY_32, algorithm="HS256")
    headers = {"authorization": f"Bearer {token}"}
    result = asyncio.run(auth.authenticate(headers))
    assert result["is_authenticated"] is True
    assert result["identity"] == "tenant_a"


def test_jwt_b2b_org_mapping(monkeypatch):
    if not jwt:
        pytest.skip("PyJWT not installed")
    monkeypatch.setenv("TENANT_ORG_MAPPINGS", '{"org_beta": "tenant_b"}')
    auth = TenantAuth(secret_key=SECRET_KEY_32)
    token = jwt.encode({"org_id": "org_beta", "sub": "enterprise_user"}, SECRET_KEY_32, algorithm="HS256")
    headers = {"authorization": f"Bearer {token}"}
    result = asyncio.run(auth.authenticate(headers))
    assert result["is_authenticated"] is True
    assert result["identity"] == "tenant_b"


def test_unauthenticated_request():
    auth = TenantAuth(secret_key=SECRET_KEY_32)
    headers = {}
    result = asyncio.run(auth.authenticate(headers))
    assert result["is_authenticated"] is False
    assert result["identity"] == "anonymous"
