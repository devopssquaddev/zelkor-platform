"""Unit tests for Aegra tenant auth handler (JWKS JWT only, no dev tokens)."""
import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.tenant_auth import TenantAuth  # noqa: E402
from common.jwt_verifier import validate_startup_config  # noqa: E402
from tests.helpers.jwt_keys import generate_rsa_keypair, write_jwks_file  # noqa: E402

pytest.importorskip("cryptography")


@pytest.fixture()
def jwt_env(tmp_path, monkeypatch):
    kp = generate_rsa_keypair("kid-1")
    jwks_dir = tmp_path / "jwks"
    jwks_dir.mkdir()
    write_jwks_file(str(jwks_dir / "jwks"), kp.jwks)
    monkeypatch.setenv("AUTH_JWKS_PATH", str(jwks_dir))
    monkeypatch.setenv("AUTH_JWT_ISSUER", "https://test.zelkor.invalid")
    monkeypatch.setenv("AUTH_JWT_AUDIENCES", '["zelkor"]')
    monkeypatch.setenv("AUTH_TENANT_CLAIMS", '["tenant_id"]')
    validate_startup_config()
    return kp


def test_rejects_dev_prefix_token(jwt_env):
    auth = TenantAuth()
    result = asyncio.run(auth.authenticate({"authorization": "Bearer dev:tenant_a"}))
    assert result["is_authenticated"] is False


def test_rejects_bare_tenant_header(jwt_env):
    auth = TenantAuth()
    result = asyncio.run(auth.authenticate({"x-tenant-id": "tenant_a"}))
    assert result["is_authenticated"] is False


def test_accepts_rs256_tenant_jwt(jwt_env):
    token = jwt_env.mint(
        "https://test.zelkor.invalid",
        ["zelkor"],
        {"tenant_id": "tenant_a"},
    )
    auth = TenantAuth()
    result = asyncio.run(auth.authenticate({"authorization": f"Bearer {token}"}))
    assert result["is_authenticated"] is True
    assert result["tenant_id"] == "tenant_a"
    assert result["mode"] == "jwt"


def test_unauthenticated_request(jwt_env):
    auth = TenantAuth()
    result = asyncio.run(auth.authenticate({}))
    assert result["is_authenticated"] is False
    assert result["identity"] == "anonymous"
