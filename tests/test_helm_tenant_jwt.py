"""C3: platform.tenants.jwt helm validation and JWKS render rules."""
from __future__ import annotations

from pathlib import Path

from tests.test_helm_values_schema import _docs, _helm

INLINE_JWKS = Path(__file__).resolve().parent / "fixtures" / "lab-inline-jwks.yaml"


def _helm_local_jwks(*extra: str):
    return _helm(
        *extra,
        "--set",
        "platform.tenants.jwt.remoteJwksUri=",
        values_files=[INLINE_JWKS],
    )


def test_jwt_empty_audiences_fails():
    r = _helm("--set", "platform.tenants.jwt.audiences=")
    assert r.returncode != 0
    assert "audiences" in r.stderr or "platform.tenants.jwt" in r.stderr


def test_jwt_missing_issuer_fails():
    r = _helm("--set", "platform.tenants.jwt.issuer=")
    assert r.returncode != 0


def test_jwt_multiple_jwks_sources_fails():
    r = _helm(
        "--set",
        "platform.tenants.jwt.remoteJwksUri=https://issuer.example/jwks",
        values_files=[INLINE_JWKS],
    )
    assert r.returncode != 0
    assert "one JWKS source" in r.stderr


def test_remote_jwks_requires_egress_cidrs_when_network_policies_enabled():
    r = _helm(
        "--set",
        "security.networkPolicies.enabled=true",
        "--set",
        "platform.tenants.jwt.jwksEgressCIDRs=",
    )
    assert r.returncode != 0
    assert "jwksEgressCIDRs" in r.stderr


def test_local_signing_without_seed_tenant_fails_when_langfuse_seed_mcp():
    r = _helm_local_jwks(
        "--set",
        "platform.tenants.jwt.localSigning.enabled=true",
        "--set",
        "platform.tenants.jwt.localSigning.seedTenant=",
        "--set",
        "platform.telemetry.langfuse.surfaces.tools.seedFromMcp=true",
    )
    assert r.returncode != 0
    assert "seedTenant" in r.stderr


def test_local_signing_enabled_without_inline_jwks_fails_at_render():
    r = _helm(
        "--set",
        "platform.tenants.jwt.localSigning.enabled=true",
        "--set",
        "platform.tenants.jwt.localSigning.seedTenant=lab",
        "--set",
        "platform.tenants.jwt.jwks=",
        "--set",
        "platform.tenants.jwt.remoteJwksUri=",
        "--set",
        "platform.tenants.jwt.issuer=https://issuer.example",
        "--set",
        "platform.tenants.jwt.audiences[0]=zelkor",
    )
    assert r.returncode != 0
    assert "jwks is required" in r.stderr


def test_signing_secret_emitted_when_local_signing_has_private_key():
    r = _helm_local_jwks(
        "--set",
        "platform.tenants.jwt.localSigning.enabled=true",
        "--set",
        "platform.tenants.jwt.localSigning.seedTenant=lab",
        "--set",
        "platform.tenants.jwt.localSigning.privateKey=-----BEGIN PRIVATE KEY-----\\nMIIB\\n-----END PRIVATE KEY-----",
    )
    assert r.returncode == 0, r.stderr
    secrets = [
        d
        for d in _docs(r.stdout)
        if d.get("kind") == "Secret" and d["metadata"]["name"].endswith("tenant-jwt-signing")
    ]
    assert len(secrets) == 1


def test_schema_rejects_jwt_secret_and_dev_tokens_keys():
    for bad_set in (
        "platform.tenants.jwtSecret=x",
        "platform.tenants.devTokens.enabled=true",
    ):
        r = _helm("--set", bad_set)
        assert r.returncode != 0


JWKS_EGRESS_POLICIES = (
    "zelkor-platform-aegra-egress",
    "zelkor-platform-mcp-postgres-egress",
    "zelkor-platform-mcp-qdrant-egress",
    "zelkor-platform-mcp-aigateway-egress",
)


def test_jwks_egress_cidrs_render_https_ipblock_on_aegra_and_mcp():
    r = _helm(
        "--set",
        "security.networkPolicies.enabled=true",
        "--set",
        "platform.tenants.jwt.jwksEgressCIDRs[0]=203.0.113.0/24",
    )
    assert r.returncode == 0, r.stderr
    found = set()
    for d in _docs(r.stdout):
        if d.get("kind") != "NetworkPolicy":
            continue
        name = d["metadata"]["name"]
        if name not in JWKS_EGRESS_POLICIES:
            continue
        blocks = []
        for rule in d["spec"].get("egress") or []:
            for dest in rule.get("to") or []:
                cidr = (dest.get("ipBlock") or {}).get("cidr")
                if cidr:
                    ports = {(p.get("protocol"), p.get("port")) for p in rule.get("ports") or []}
                    blocks.append((cidr, ports))
        assert ("203.0.113.0/24", {("TCP", 443)}) in blocks, name
        found.add(name)
    assert found == set(JWKS_EGRESS_POLICIES)
