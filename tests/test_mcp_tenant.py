import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "mcp")))
from common.tenant import extract_tenant


def test_extract_tenant_empty_without_config(monkeypatch):
    monkeypatch.delenv("AUTH_DEV_TOKENS_ENABLED", raising=False)
    monkeypatch.delenv("AUTH_DEV_TOKEN_PREFIX", raising=False)
    monkeypatch.delenv("AUTH_TRUST_TENANT_HEADER", raising=False)
    assert extract_tenant({"Authorization": "Bearer dev:tenant_a"}) is None
    assert extract_tenant({"X-Tenant-ID": "tenant_a"}) is None
    assert extract_tenant({"Authorization": "Bearer some-api-key"}) is None


def test_extract_tenant_configured_prefix(monkeypatch):
    monkeypatch.setenv("AUTH_DEV_TOKENS_ENABLED", "true")
    monkeypatch.setenv("AUTH_DEV_TOKEN_PREFIX", "dev:")
    assert extract_tenant({"Authorization": "Bearer dev:tenant_a"}) == "tenant_a"
    assert extract_tenant({"Authorization": "Bearer other:tenant_a"}) is None


def test_extract_tenant_configured_header(monkeypatch):
    monkeypatch.setenv("AUTH_TRUST_TENANT_HEADER", "true")
    assert extract_tenant({"X-Tenant-ID": "tenant_b"}) == "tenant_b"


def test_extract_tenant_prefix_required_when_enabled(monkeypatch):
    monkeypatch.setenv("AUTH_DEV_TOKENS_ENABLED", "true")
    monkeypatch.setenv("AUTH_DEV_TOKEN_PREFIX", "")
    assert extract_tenant({"Authorization": "Bearer dev:tenant_a"}) is None


def test_extract_tenant_jwt(monkeypatch):
    jwt = pytest.importorskip("jwt")
    secret = "zelkor-test-jwt-secret-32bytes-min"
    monkeypatch.setenv("AUTH_JWT_SECRET", secret)
    token = jwt.encode({"tenant_id": "tenant_a", "sub": "user_123"}, secret, algorithm="HS256")
    assert extract_tenant({"Authorization": f"Bearer {token}"}) == "tenant_a"


def test_extract_tenant_jwt_org_mapping(monkeypatch):
    jwt = pytest.importorskip("jwt")
    secret = "zelkor-test-jwt-secret-32bytes-min"
    monkeypatch.setenv("AUTH_JWT_SECRET", secret)
    monkeypatch.setenv("TENANT_ORG_MAPPINGS", '{"org_beta": "tenant_b"}')
    token = jwt.encode({"org_id": "org_beta"}, secret, algorithm="HS256")
    assert extract_tenant({"Authorization": f"Bearer {token}"}) == "tenant_b"


def test_extract_tenant_jwt_rejects_wrong_signature(monkeypatch):
    jwt = pytest.importorskip("jwt")
    monkeypatch.setenv("AUTH_JWT_SECRET", "zelkor-test-jwt-secret-32bytes-min")
    token = jwt.encode(
        {"tenant_id": "tenant_a"},
        "other-secret-key-32bytes-min!!!",
        algorithm="HS256",
    )
    assert extract_tenant({"Authorization": f"Bearer {token}"}) is None


def test_extract_tenant_jwt_falls_through_to_dev_token(monkeypatch):
    monkeypatch.setenv("AUTH_JWT_SECRET", "zelkor-test-jwt-secret-32bytes-min")
    monkeypatch.setenv("AUTH_DEV_TOKENS_ENABLED", "true")
    monkeypatch.setenv("AUTH_DEV_TOKEN_PREFIX", "dev:")
    assert extract_tenant({"Authorization": "Bearer dev:tenant_a"}) == "tenant_a"
