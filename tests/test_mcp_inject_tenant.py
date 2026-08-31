"""Unit tests for Mode B tenant identity (no cluster, no MCP adapters)."""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "images" / "aegra"))

from mcp_inject import _stamp_tenant_kwargs, tenant_from_run_config  # noqa: E402


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


def test_tenant_from_aegra_user_id_fallback():
    cfg = {"configurable": {"user_id": "Bank_Alpha"}}
    assert tenant_from_run_config(cfg) == "Bank_Alpha"


def test_tenant_from_run_config_ignores_empty():
    assert tenant_from_run_config({}) == ""
    assert tenant_from_run_config(None) == ""


def test_stamp_tenant_kwargs_overwrites_model_guess(monkeypatch):
    monkeypatch.setattr(
        "mcp_inject.tenant_from_run_config", lambda config=None: "Bank_Alpha"
    )
    assert _stamp_tenant_kwargs({"tenant_id": "current_user", "sql": "SELECT 1"})[
        "tenant_id"
    ] == "Bank_Alpha"
