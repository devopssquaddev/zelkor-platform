"""Unit tests for Mode B tenant identity (no cluster, no MCP adapters)."""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "images" / "aegra"))

from mcp_inject import (  # noqa: E402
    _stamp_tenant_kwargs,
    _stamp_tenant_on_tool,
    identity_headers,
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
        assert tenant_from_run_config(None) == "Bank_Alpha"
        headers = identity_headers({})
        assert headers["X-Tenant-ID"] == "Bank_Alpha"
    finally:
        reset_auth_user(token)
    assert tenant_from_run_config({}) == ""
    assert "X-Tenant-ID" not in identity_headers({})


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
        assert headers["X-Tenant-ID"] == "Bank_Alpha"
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


def test_auth_user_wins_over_client_and_model_fields(monkeypatch):
    monkeypatch.setenv("AUTH_DEV_TOKEN_PREFIX", "dev:")
    token = bind_auth_user({"tenant_id": "Bank_Alpha", "identity": "Bank_Alpha"})
    try:
        cfg = {"configurable": {"user_id": "finserve", "tenant_id": "finserve"}}
        assert tenant_from_run_config(cfg) == "Bank_Alpha"
        stamped = _stamp_tenant_kwargs({"tenant_id": "finserve", "query": "x"})
        assert stamped["tenant_id"] == "Bank_Alpha"
        headers = identity_headers(cfg)
        assert headers["X-Tenant-ID"] == "Bank_Alpha"
        assert headers["Authorization"] == "Bearer dev:Bank_Alpha"
    finally:
        reset_auth_user(token)


def test_no_auth_user_no_tenant_headers(monkeypatch):
    monkeypatch.setenv("AUTH_DEV_TOKEN_PREFIX", "dev:")
    monkeypatch.setenv("ZELKOR_TENANT_ID", "Bank_Beta")
    headers = identity_headers({"configurable": {"user_id": "Bank_Beta"}})
    assert "X-Tenant-ID" not in headers
    assert "Authorization" not in headers


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


def test_stamp_tenant_kwargs_overwrites_model_guess(monkeypatch):
    monkeypatch.setattr(
        "mcp_inject.tenant_from_run_config", lambda config=None: "Bank_Alpha"
    )
    assert _stamp_tenant_kwargs({"tenant_id": "current_user", "sql": "SELECT 1"})[
        "tenant_id"
    ] == "Bank_Alpha"


class _FakeTool:
    def __init__(
        self,
        *,
        func=None,
        coroutine=None,
        name="postgres__query",
        response_format=None,
    ):
        self.func = func
        self.coroutine = coroutine
        self.name = name
        self.handle_tool_error = None
        self.response_format = response_format

    def model_copy(self, update=None):
        next_tool = _FakeTool(
            func=self.func,
            coroutine=self.coroutine,
            name=self.name,
            response_format=self.response_format,
        )
        next_tool.handle_tool_error = self.handle_tool_error
        for key, value in (update or {}).items():
            setattr(next_tool, key, value)
        return next_tool


def test_stamp_tenant_on_tool_returns_exception_as_content(monkeypatch):
    monkeypatch.setattr(
        "mcp_inject.tenant_from_run_config", lambda config=None: "Bank_Alpha"
    )

    def boom(**kwargs):
        assert kwargs["tenant_id"] == "Bank_Alpha"
        raise RuntimeError('relation "portfolio" does not exist')

    wrapped = _stamp_tenant_on_tool(_FakeTool(func=boom))
    text = wrapped.func(sql="SELECT 1", tenant_id="current")
    assert text.startswith("Error: RuntimeError:")
    assert "portfolio" in text
    assert wrapped.handle_tool_error is True


def test_stamp_tenant_on_tool_content_and_artifact_tuple(monkeypatch):
    monkeypatch.setattr(
        "mcp_inject.tenant_from_run_config", lambda config=None: "Bank_Alpha"
    )

    def boom(**kwargs):
        raise RuntimeError('column "valuation" does not exist')

    wrapped = _stamp_tenant_on_tool(
        _FakeTool(func=boom, response_format="content_and_artifact")
    )
    content, artifact = wrapped.func(sql="SELECT 1", tenant_id="current")
    assert content.startswith("Error: RuntimeError:")
    assert artifact is None
