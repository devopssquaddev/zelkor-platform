"""Unit tests for Mode B bearer / tenant identity (no MCP session)."""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "images" / "aegra"))

from mcp_inject import (  # noqa: E402
    identity_headers,
    inbound_authorization,
    tenant_from_run_config,
)
from wrap_identity import (  # noqa: E402
    bind_auth_user,
    current_auth_identity,
    reset_auth_user,
)


def test_tenant_from_auth_user_dict():
    cfg = {
        "configurable": {
            "langgraph_auth_user": {"identity": "Bank_Alpha", "tenant_id": "Bank_Alpha"}
        }
    }
    assert tenant_from_run_config(cfg) == "Bank_Alpha"


def test_tenant_from_auth_user_object():
    user = SimpleNamespace(identity="Bank_Alpha", tenant_id="Bank_Alpha")
    cfg = {"configurable": {"langgraph_auth_user": user}}
    assert tenant_from_run_config(cfg) == "Bank_Alpha"


def test_tenant_ignores_client_user_id():
    cfg = {"configurable": {"user_id": "Bank_Alpha", "tenant_id": "finserve"}}
    assert tenant_from_run_config(cfg) == ""


def test_tenant_from_run_config_ignores_empty():
    assert tenant_from_run_config({}) == ""
    assert tenant_from_run_config(None) == ""


def test_bound_auth_user_when_get_config_empty():
    token = bind_auth_user({"tenant_id": "Bank_Alpha", "identity": "Bank_Alpha"})
    try:
        assert current_auth_identity() == "Bank_Alpha"
        assert tenant_from_run_config({}) == "Bank_Alpha"
    finally:
        reset_auth_user(token)


def test_identity_headers_forwards_inbound_authorization(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "consumer-key")
    monkeypatch.delenv("AUTH_DEV_TOKEN_PREFIX", raising=False)
    inbound = "Bearer eyJhbGciOiJIUzI1NiJ9.tenant"
    token = bind_auth_user(
        {
            "tenant_id": "Bank_Alpha",
            "identity": "Bank_Alpha",
            "authorization": inbound,
        }
    )
    try:
        headers = identity_headers({})
        assert "X-Tenant-ID" not in headers
        assert headers["Authorization"] == inbound
        assert headers["Authorization"] != "Bearer consumer-key"
    finally:
        reset_auth_user(token)


def test_identity_headers_forwards_from_config_user(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "consumer-key")
    inbound = "Bearer eyJhbGciOiJIUzI1NiJ9.tenant"
    cfg = {
        "configurable": {
            "langgraph_auth_user": {
                "tenant_id": "Bank_Alpha",
                "identity": "Bank_Alpha",
                "authorization": inbound,
            }
        }
    }
    headers = identity_headers(cfg)
    assert headers["Authorization"] == inbound
    assert "X-Tenant-ID" not in headers


def test_inbound_authorization_uses_mcp_auth_token_bootstrap(monkeypatch):
    monkeypatch.delenv("AUTH_DEV_TOKEN_PREFIX", raising=False)
    monkeypatch.setenv("MCP_AUTH_TOKEN", "service-secret")
    assert inbound_authorization({}) == "Bearer service-secret"


def test_no_auth_user_no_authorization_header(monkeypatch):
    monkeypatch.delenv("MCP_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("AUTH_DEV_TOKEN_PREFIX", raising=False)
    headers = identity_headers({"configurable": {"user_id": "Bank_Beta"}})
    assert "Authorization" not in headers
    assert "X-Tenant-ID" not in headers


def test_sitecustomize_and_dockerfile_ship_wrap_identity():
    root = Path(__file__).resolve().parents[1]
    site = (root / "images/aegra/sitecustomize.py").read_text()
    dockerfile = (root / "images/aegra/Dockerfile").read_text()
    assert "from wrap_identity import patch_pregel" in site
    assert "wrap_identity.py" in dockerfile


def test_mode_b_does_not_wrap_create_deep_agent():
    text = Path(__file__).resolve().parents[1].joinpath("images/aegra/mcp_inject.py").read_text()
    assert "create_agent" in text
    assert "create_deep_agent" not in text
