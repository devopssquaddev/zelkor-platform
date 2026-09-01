"""Unit tests for wrap auth.path inject (no cluster)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "images" / "aegra"))

from auth_inject import ensure_auth_config  # noqa: E402


def test_ensure_auth_config_injects_missing_path(tmp_path, monkeypatch):
    cfg = tmp_path / "aegra.json"
    cfg.write_text('{"graphs": {"x": "./x.py:graph"}}', encoding="utf-8")
    dest = tmp_path / "with-auth.json"
    monkeypatch.setenv("AEGRA_AUTH_CONFIG", str(dest))
    out = ensure_auth_config(str(cfg))
    assert dest.is_file()
    data = json.loads(dest.read_text(encoding="utf-8"))
    assert data["auth"]["path"] == "./tenant_auth.py:auth"
    assert data["graphs"]["x"] == "./x.py:graph"
    assert out == str(dest)


def test_ensure_auth_config_keeps_existing_path(tmp_path):
    cfg = tmp_path / "aegra.json"
    cfg.write_text(
        '{"graphs": {}, "auth": {"path": "./custom.py:auth"}}',
        encoding="utf-8",
    )
    out = ensure_auth_config(str(cfg))
    assert out == str(cfg)
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["auth"]["path"] == "./custom.py:auth"


def test_sitecustomize_injects_auth_before_aegra_import():
    text = (Path(__file__).resolve().parents[1] / "images/aegra/sitecustomize.py").read_text()
    assert "ensure_auth_config" in text
    assert "openai_compat" not in text
    assert "patch_httpx" not in text
    assert text.find("ensure_auth_config") < text.find("FastAPI")


def test_ensure_auth_config_discovers_langgraph_when_aegra_config_missing(tmp_path, monkeypatch):
    lg = tmp_path / "langgraph.json"
    lg.write_text(
        '{"graphs": {"agent": "./zelkor_deep_factory.py:graph"}}',
        encoding="utf-8",
    )
    dest = tmp_path / "with-auth.json"
    monkeypatch.setenv("AEGRA_CONFIG", str(tmp_path / "missing-aegra.json"))
    monkeypatch.setenv("AEGRA_AUTH_CONFIG", str(dest))
    import auth_inject as mod

    monkeypatch.setattr(mod, "_DISCOVER", (str(tmp_path / "aegra.json"), str(lg)))
    out = mod.ensure_auth_config()
    assert dest.is_file()
    data = json.loads(dest.read_text(encoding="utf-8"))
    assert data["auth"]["path"] == "./tenant_auth.py:auth"
    assert data["graphs"]["agent"] == "./zelkor_deep_factory.py:graph"
    assert out == str(dest)
