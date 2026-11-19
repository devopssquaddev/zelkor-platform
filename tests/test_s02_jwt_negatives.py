"""S-02 (P2) L1: every forged or invalid north-south token is refused by the shared JWKS verifier
and by Aegra TenantAuth. One positive control proves the fixture can accept a good token, so a
rejection here is the verifier's decision, not a broken setup."""
from __future__ import annotations

import asyncio
import base64
import functools
import hashlib
import hmac
import json
import sys
import time
from pathlib import Path

import jwt
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import common.jwt_verifier as jv  # noqa: E402
from agents.tenant_auth import TenantAuth  # noqa: E402
from tests.helpers.jwt_keys import generate_rsa_keypair, write_jwks_file  # noqa: E402

pytest.importorskip("cryptography")

ISS = "https://test.zelkor.invalid"
AUD = ["zelkor"]


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _raw(header: dict, payload: dict, sign) -> str:
    head = _b64(json.dumps(header).encode()) + "." + _b64(json.dumps(payload).encode())
    return head + "." + sign(head.encode())


def _claims(**over) -> dict:
    now = int(time.time())
    return {"iss": ISS, "aud": AUD, "iat": now, "exp": now + 3600, "tenant_id": "tenant_a", **over}


@functools.lru_cache(maxsize=None)
def _keypair(name: str, kid: str):
    return generate_rsa_keypair(kid)


@pytest.fixture()
def keys(tmp_path, monkeypatch):
    trusted = _keypair("trusted", "kid-1")
    jwks_dir = tmp_path / "jwks"
    jwks_dir.mkdir()
    write_jwks_file(str(jwks_dir / "jwks"), trusted.jwks)
    monkeypatch.setenv("AUTH_JWKS_PATH", str(jwks_dir))
    monkeypatch.setenv("AUTH_JWT_ISSUER", ISS)
    monkeypatch.setenv("AUTH_JWT_AUDIENCES", json.dumps(AUD))
    monkeypatch.setenv("AUTH_TENANT_CLAIMS", '["tenant_id"]')
    monkeypatch.setattr(jv, "_jwks_cache", {})
    monkeypatch.setattr(jv, "_jwks_mtime", 0.0)
    monkeypatch.setattr(jv, "_last_kid_reload", 0.0)
    return trusted


def _public_pem(kp) -> bytes:
    from cryptography.hazmat.primitives import serialization

    return serialization.load_pem_private_key(kp.private_pem, None).public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)


def _variants(trusted) -> dict[str, str]:
    """name -> Authorization header value. Every one must be refused."""
    stranger = _keypair("stranger", "kid-1")  # same kid, key not in the JWKS
    unknown_kid = _keypair("unknown", "kid-other")
    pub = _public_pem(trusted)
    rs = lambda kp, claims, **h: jwt.encode(claims, kp.private_pem, algorithm="RS256",  # noqa: E731
                                            headers={"kid": kp.kid, **h})
    good = _claims()
    no_exp = {k: v for k, v in good.items() if k != "exp"}
    return {
        "alg_none": "Bearer " + _raw({"alg": "none", "typ": "JWT", "kid": "kid-1"}, good, lambda _: ""),
        "alg_none_uppercase": "Bearer " + _raw({"alg": "NONE", "kid": "kid-1"}, good, lambda _: ""),
        "hs256_signed_with_public_key": "Bearer " + _raw(
            {"alg": "HS256", "typ": "JWT", "kid": "kid-1"}, good,
            lambda m: _b64(hmac.new(pub, m, hashlib.sha256).digest())),
        "rs256_key_not_in_jwks_same_kid": "Bearer " + rs(stranger, good),
        "rs256_unknown_kid": "Bearer " + rs(unknown_kid, good),
        "rs256_no_kid_untrusted_key": "Bearer " + jwt.encode(good, stranger.private_pem, algorithm="RS256"),
        "expired": "Bearer " + rs(trusted, _claims(iat=int(time.time()) - 7200, exp=int(time.time()) - 60)),
        "no_exp": "Bearer " + rs(trusted, no_exp),
        "wrong_audience": "Bearer " + rs(trusted, _claims(aud=["someone-else"])),
        "wrong_issuer": "Bearer " + rs(trusted, _claims(iss="https://attacker.invalid")),
        "tampered_payload": "Bearer " + _tamper(rs(trusted, good)),
        "dev_prefix": "Bearer dev:tenant_a",
        "not_a_jwt": "Bearer tenant_a",
        "no_bearer_scheme": rs(trusted, good),
        "empty_bearer": "Bearer ",
    }


def _tamper(token: str) -> str:
    head, payload, sig = token.split(".")
    claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    claims["tenant_id"] = "tenant_b"
    return ".".join([head, _b64(json.dumps(claims).encode()), sig])


VARIANTS = ["alg_none", "alg_none_uppercase", "hs256_signed_with_public_key", "rs256_key_not_in_jwks_same_kid",
            "rs256_unknown_kid", "rs256_no_kid_untrusted_key", "expired", "no_exp", "wrong_audience",
            "wrong_issuer", "tampered_payload", "dev_prefix", "not_a_jwt", "no_bearer_scheme", "empty_bearer"]


def test_s02_positive_control_accepts_a_trusted_token(keys):
    token = keys.mint(ISS, AUD, {"tenant_id": "tenant_a"})
    assert jv.verify_bearer(f"Bearer {token}")["tenant_id"] == "tenant_a"
    result = asyncio.run(TenantAuth().authenticate({"authorization": f"Bearer {token}"}))
    assert result["is_authenticated"] is True and result["tenant_id"] == "tenant_a"


def test_s02_variant_list_is_complete(keys):
    assert sorted(_variants(keys)) == sorted(VARIANTS)


@pytest.mark.parametrize("variant", VARIANTS)
def test_s02_verifier_refuses(keys, variant):
    authz = _variants(keys)[variant]
    with pytest.raises(Exception) as exc:
        jv.verify_bearer(authz)
    assert not isinstance(exc.value, (AssertionError, KeyboardInterrupt))


@pytest.mark.parametrize("variant", VARIANTS)
def test_s02_aegra_tenant_auth_refuses(keys, variant):
    authz = _variants(keys)[variant]
    result = asyncio.run(TenantAuth().authenticate({"authorization": authz}))
    assert result["is_authenticated"] is False, variant
    assert result["tenant_id"] is None


def test_s02_header_only_identity_is_refused(keys):
    result = asyncio.run(TenantAuth().authenticate({"x-tenant-id": "tenant_a", "x-zelkor-claim-sub": "u"}))
    assert result["is_authenticated"] is False
