"""Generate RSA key, JWKS JSON, and seed JWT for localSigning (host only; no cluster API)."""
from __future__ import annotations

import argparse
import base64
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import jwt
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
except ImportError as exc:
    raise SystemExit(f"jwt generate dependencies missing: {exc}") from exc


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _parse_ttl(raw: str) -> timedelta:
    raw = (raw or "24h").strip()
    if raw.endswith("h"):
        return timedelta(hours=int(raw[:-1]))
    if raw.endswith("m"):
        return timedelta(minutes=int(raw[:-1]))
    if raw.endswith("d"):
        return timedelta(days=int(raw[:-1]))
    return timedelta(hours=24)


def generate_rsa(kid: str) -> tuple[bytes, dict]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub = key.public_key().public_numbers()
    n = _b64url(pub.n.to_bytes((pub.n.bit_length() + 7) // 8, "big"))
    e = _b64url(pub.e.to_bytes((pub.e.bit_length() + 7) // 8, "big"))
    jwks = {"keys": [{"kty": "RSA", "kid": kid, "use": "sig", "alg": "RS256", "n": n, "e": e}]}
    return priv_pem, jwks


def jwks_from_private(priv_pem: bytes, kid: str) -> dict:
    key = load_pem_private_key(priv_pem, password=None)
    pub = key.public_key().public_numbers()
    n = _b64url(pub.n.to_bytes((pub.n.bit_length() + 7) // 8, "big"))
    e = _b64url(pub.e.to_bytes((pub.e.bit_length() + 7) // 8, "big"))
    return {"keys": [{"kty": "RSA", "kid": kid, "use": "sig", "alg": "RS256", "n": n, "e": e}]}


def mint_seed_token(
    priv_pem: bytes,
    kid: str,
    issuer: str,
    audiences: list[str],
    seed_tenant: str,
    seed_ttl: str,
) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "iss": issuer,
            "aud": audiences,
            "tenant_id": seed_tenant,
            "exp": now + _parse_ttl(seed_ttl),
            "iat": now,
        },
        priv_pem,
        algorithm="RS256",
        headers={"kid": kid},
    )


def ensure_material(
    state_dir: Path,
    issuer: str,
    audiences: list[str],
    seed_tenant: str,
    seed_ttl: str,
    rotation_id: str,
) -> tuple[Path, Path, str]:
    state_dir.mkdir(parents=True, exist_ok=True)
    priv_path = state_dir / "private.pem"
    jwks_path = state_dir / "jwks.json"
    kid_path = state_dir / "kid.txt"

    if priv_path.is_file():
        priv_pem = priv_path.read_bytes()
        kid = kid_path.read_text().strip() if kid_path.is_file() else f"zelkor-{rotation_id}"
    else:
        kid = f"zelkor-{rotation_id}"
        priv_pem, jwks = generate_rsa(kid)
        priv_path.write_bytes(priv_pem)
        jwks_path.write_text(json.dumps(jwks))
        (state_dir / "jwks.txt").write_text(json.dumps(jwks))
        kid_path.write_text(kid)

    if not jwks_path.is_file():
        jwks_doc = jwks_from_private(priv_pem, kid)
        jwks_path.write_text(json.dumps(jwks_doc))
        (state_dir / "jwks.txt").write_text(json.dumps(jwks_doc))
    elif not (state_dir / "jwks.txt").is_file():
        (state_dir / "jwks.txt").write_text(jwks_path.read_text())

    token = mint_seed_token(priv_pem, kid, issuer, audiences, seed_tenant, seed_ttl)
    return priv_path, jwks_path, token


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate localSigning material for Helm")
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--issuer", required=True)
    parser.add_argument("--audiences", default='["zelkor"]')
    parser.add_argument("--seed-tenant", required=True)
    parser.add_argument("--seed-ttl", default="24h")
    parser.add_argument("--rotation-id", default="1")
    parser.add_argument("--print-seed-token", action="store_true")
    args = parser.parse_args()
    aud = json.loads(args.audiences) if args.audiences.startswith("[") else [args.audiences]
    _, _, token = ensure_material(
        Path(args.state_dir),
        args.issuer,
        aud,
        args.seed_tenant,
        args.seed_ttl,
        args.rotation_id,
    )
    if args.print_seed_token:
        sys.stdout.write(token)


if __name__ == "__main__":
    main()
