"""S-02 (P2) L3: the Aegra front door answers 401/403 to every forged or invalid token, signed with
the lab release's real key where the variant needs a valid signature (expired, wrong aud/iss, no
exp, tampered, HS256 keyed with the public key). A lab-signed good token is the positive control."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

import httpx
import jwt
import pytest

from tests.helpers.lab_jwt import signing_material
from tests.test_s02_jwt_negatives import _b64, _keypair, _raw, _tamper

HOST = os.environ.get("AGENTS_HOST_HEADER") or os.environ.get("AEGRA_HOST_HEADER", "agents.localhost")
BASE = os.environ.get("GATEWAY_BASE_URL", "http://127.0.0.1:8088")


@pytest.fixture(scope="module")
def lab():
    if not os.environ.get("KUBECONTEXT"):
        pytest.skip("KUBECONTEXT not set")
    key, kid, iss, aud = signing_material()
    from cryptography.hazmat.primitives import serialization

    pub = serialization.load_pem_private_key(key, None).public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    return key, kid, iss, aud, pub


def _claims(iss, aud, **over):
    now = int(time.time())
    return {"iss": iss, "aud": aud, "iat": now, "exp": now + 900, "tenant_id": "tenant-a", **over}


def _variants(lab) -> dict[str, str]:
    key, kid, iss, aud, pub = lab
    good = _claims(iss, aud)
    signed = lambda c, **h: jwt.encode(c, key, algorithm="RS256", headers={"kid": kid, **h})  # noqa: E731
    stranger = _keypair("stranger", kid)
    return {
        "alg_none": "Bearer " + _raw({"alg": "none", "kid": kid}, good, lambda _: ""),
        "hs256_signed_with_public_key": "Bearer " + _raw({"alg": "HS256", "kid": kid}, good,
                                                         lambda m: _b64(hmac.new(pub, m, hashlib.sha256).digest())),
        "untrusted_key_same_kid": "Bearer " + jwt.encode(good, stranger.private_pem, algorithm="RS256",
                                                         headers={"kid": kid}),
        "expired": "Bearer " + signed(_claims(iss, aud, iat=int(time.time()) - 7200, exp=int(time.time()) - 60)),
        "no_exp": "Bearer " + signed({k: v for k, v in good.items() if k != "exp"}),
        "wrong_audience": "Bearer " + signed(_claims(iss, ["someone-else"])),
        "wrong_issuer": "Bearer " + signed(_claims("https://attacker.invalid", aud)),
        "tampered_tenant": "Bearer " + _tamper(signed(good)),
        "dev_prefix": "Bearer dev:tenant-a",
        "no_scheme": signed(good),
    }


def _post_thread(authz: str | None, **extra_headers: str) -> httpx.Response:
    headers = {"Host": HOST, **extra_headers}
    if authz is not None:
        headers["Authorization"] = authz
    try:
        return httpx.post(f"{BASE}/threads", json={}, headers=headers, timeout=30.0)
    except httpx.ConnectError as exc:
        pytest.skip(f"gateway not reachable: {exc}")


def test_s02_positive_control_lab_signed_token_is_accepted(lab):
    key, kid, iss, aud, _ = lab
    r = _post_thread("Bearer " + jwt.encode(_claims(iss, aud), key, algorithm="RS256", headers={"kid": kid}))
    assert r.status_code == 200, r.text[:200]


@pytest.mark.parametrize("variant", ["alg_none", "hs256_signed_with_public_key", "untrusted_key_same_kid", "expired",
                                     "no_exp", "wrong_audience", "wrong_issuer", "tampered_tenant", "dev_prefix",
                                     "no_scheme"])
def test_s02_front_door_refuses(lab, variant):
    r = _post_thread(_variants(lab)[variant])
    assert r.status_code in (401, 403), f"{variant}: {r.status_code} {r.text[:200]}"


def test_s02_header_only_identity_is_refused(lab):
    r = _post_thread(None, **{"X-Tenant-ID": "tenant-a"})
    assert r.status_code in (401, 403), r.text[:200]
