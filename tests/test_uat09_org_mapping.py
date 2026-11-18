"""UAT-09 L1: org_id-only JWTs map to a tenant through TENANT_ORG_MAPPINGS (Helm
platform.tenants.orgMappings). An unmapped org becomes its own tenant and never lands in a mapped
one; claim order decides which claim wins. Live half (unmapped org gets 404 on tenant-a's thread)
runs in the S-gate."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import common.jwt_verifier as jv  # noqa: E402
from tests.helpers.jwt_keys import generate_rsa_keypair, write_jwks_file  # noqa: E402

pytest.importorskip("cryptography")

ISS = "https://test.zelkor.invalid"
KP = generate_rsa_keypair("kid-1")


@pytest.fixture()
def env(tmp_path, monkeypatch):
    d = tmp_path / "jwks"
    d.mkdir()
    write_jwks_file(str(d / "jwks"), KP.jwks)
    monkeypatch.setenv("AUTH_JWKS_PATH", str(d))
    monkeypatch.setenv("AUTH_JWT_ISSUER", ISS)
    monkeypatch.setenv("AUTH_JWT_AUDIENCES", '["zelkor"]')
    monkeypatch.setenv("AUTH_TENANT_CLAIMS", '["tenant_id","org_id","sub"]')
    monkeypatch.setenv("TENANT_ORG_MAPPINGS", json.dumps({"org_alpha": "tenant-a"}))
    monkeypatch.setattr(jv, "_jwks_cache", {})
    monkeypatch.setattr(jv, "_jwks_mtime", 0.0)
    return monkeypatch


def _tenant(claims: dict, **headers: str) -> str:
    token = KP.mint(ISS, ["zelkor"], claims)
    return jv.resolve_tenant_from_headers({"authorization": f"Bearer {token}", **headers})


def test_uat09_mapped_org_resolves_to_its_tenant(env):
    assert _tenant({"org_id": "org_alpha"}) == "tenant-a"


def test_uat09_unmapped_org_is_its_own_tenant_not_a_mapped_one(env):
    assert _tenant({"org_id": "org_beta"}) == "org_beta"
    assert _tenant({"org_id": "org_alpha_x"}) == "org_alpha_x"  # no prefix match


def test_uat09_claim_order_decides(env):
    assert _tenant({"tenant_id": "tenant-b", "org_id": "org_alpha"}) == "tenant-b"
    env.setenv("AUTH_TENANT_CLAIMS", '["org_id","tenant_id"]')
    assert _tenant({"tenant_id": "tenant-b", "org_id": "org_alpha"}) == "tenant-a"


def test_uat09_forged_org_header_is_rejected(env):
    with pytest.raises(PermissionError, match="identity mismatch"):
        _tenant({"org_id": "org_beta"}, **{"x-zelkor-claim-org-id": "org_alpha"})


def test_uat09_no_tenant_claim_is_rejected(env):
    env.setenv("AUTH_TENANT_CLAIMS", '["org_id"]')
    with pytest.raises(PermissionError, match="no tenant claim"):
        _tenant({"sub": "user-1"})


def test_uat09_bad_mapping_json_maps_nothing(env):
    env.setenv("TENANT_ORG_MAPPINGS", "{not json")
    assert _tenant({"org_id": "org_alpha"}) == "org_alpha"
