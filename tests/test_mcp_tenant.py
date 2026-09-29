import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "mcp")))
from common.jwt_verifier import validate_startup_config  # noqa: E402
from common.tenant import extract_tenant  # noqa: E402
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


def test_extract_tenant_empty_without_jwt(jwt_env):
    assert extract_tenant({}) is None
    assert extract_tenant({"Authorization": "Bearer not-a-jwt"}) is None


def test_extract_tenant_from_rs256(jwt_env):
    token = jwt_env.mint(
        "https://test.zelkor.invalid",
        ["zelkor"],
        {"tenant_id": "tenant_a"},
    )
    assert extract_tenant({"Authorization": f"Bearer {token}"}) == "tenant_a"


def test_extract_tenant_rejects_wrong_issuer(jwt_env):
    token = jwt_env.mint(
        "https://other.invalid",
        ["zelkor"],
        {"tenant_id": "tenant_a"},
    )
    assert extract_tenant({"Authorization": f"Bearer {token}"}) is None
