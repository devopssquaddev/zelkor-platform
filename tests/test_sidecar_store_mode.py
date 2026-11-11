"""CE-15a-2: sidecar store selection — stateless MemoryStore (no DB) vs PgStore."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "images" / "sidecar"))

from zelkor_sidecar.main import build_store  # noqa: E402
from zelkor_sidecar.store import MemoryStore  # noqa: E402


def test_memory_mode_needs_no_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert isinstance(build_store("memory"), MemoryStore)


def test_memory_mode_from_env(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("ZELKOR_SIDECAR_STORE", "memory")
    assert isinstance(build_store(), MemoryStore)


def test_pg_mode_without_dsn_exits(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("ZELKOR_SIDECAR_STORE", "pg")
    with pytest.raises(SystemExit):
        build_store()
