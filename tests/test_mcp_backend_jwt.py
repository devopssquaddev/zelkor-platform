import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mcp"))

from common.jwt_verifier import validate_startup_config, verify_bearer  # noqa: E402
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
    token = kp.mint("https://test.zelkor.invalid", ["zelkor"], {"tenant_id": "tenant-a"})
    return token


def test_verify_bearer_accepts_rs256(jwt_env):
    claims = verify_bearer(f"Bearer {jwt_env}")
    assert claims["tenant_id"] == "tenant-a"


def test_verify_bearer_rejects_wrong_aud(jwt_env, monkeypatch):
    monkeypatch.setenv("AUTH_JWT_AUDIENCES", '["other"]')
    with pytest.raises(Exception):
        verify_bearer(f"Bearer {jwt_env}")
