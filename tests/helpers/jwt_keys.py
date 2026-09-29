"""Ephemeral RSA keys for offline JWT tests."""
from __future__ import annotations

import json
from dataclasses import dataclass

import jwt

try:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
except ImportError:
    rsa = None  # type: ignore
    serialization = None  # type: ignore


@dataclass
class TestKeypair:
    private_pem: bytes
    jwks: dict
    kid: str

    def mint(self, issuer: str, audiences: list[str], claims: dict, ttl_hours: int = 1) -> str:
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)
        payload = {
            "iss": issuer,
            "aud": audiences,
            "exp": now + timedelta(hours=ttl_hours),
            "iat": now,
            **claims,
        }
        return jwt.encode(payload, self.private_pem, algorithm="RS256", headers={"kid": self.kid})


def generate_rsa_keypair(kid: str = "test-1") -> TestKeypair:
    if rsa is None:
        raise RuntimeError("cryptography is required for jwt_keys tests")
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub = key.public_key().public_numbers()
    import base64

    def b64url(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

    n = b64url(pub.n.to_bytes((pub.n.bit_length() + 7) // 8, "big"))
    e = b64url(pub.e.to_bytes((pub.e.bit_length() + 7) // 8, "big"))
    jwks = {"keys": [{"kty": "RSA", "kid": kid, "use": "sig", "alg": "RS256", "n": n, "e": e}]}
    return TestKeypair(private_pem=priv_pem, jwks=jwks, kid=kid)


def write_jwks_file(path: str, jwks: dict) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(jwks, fh)
