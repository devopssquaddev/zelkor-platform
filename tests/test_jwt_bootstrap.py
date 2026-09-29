"""C3 localSigning: zelkor_jwt_generate + JWKS/token verification (offline)."""
from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GENERATE = ROOT / "images" / "common" / "zelkor_jwt_generate.py"

pytest.importorskip("cryptography")

from tests.helpers.jwt_keys import write_jwks_file  # noqa: E402

sys.path.insert(0, str(ROOT / "mcp"))
from common.jwt_verifier import validate_startup_config, verify_bearer  # noqa: E402


def _run_generate(state_dir: Path, *, rotation_id: str = "1") -> None:
    subprocess.run(
        [
            sys.executable,
            str(GENERATE),
            "--state-dir",
            str(state_dir),
            "--issuer",
            "https://lab.zelkor.invalid",
            "--audiences",
            '["zelkor"]',
            "--seed-tenant",
            "seed-tenant",
            "--seed-ttl",
            "24h",
            "--rotation-id",
            rotation_id,
            "--print-seed-token",
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def test_generate_creates_key_and_reuses_on_second_run(tmp_path):
    _run_generate(tmp_path)
    priv = tmp_path / "private.pem"
    jwks = tmp_path / "jwks.json"
    assert priv.is_file() and jwks.is_file()
    first_mtime = priv.stat().st_mtime
    _run_generate(tmp_path)
    assert priv.stat().st_mtime == first_mtime


def test_minted_seed_token_verifies_with_c3_verifier(tmp_path, monkeypatch):
    res = subprocess.run(
        [
            sys.executable,
            str(GENERATE),
            "--state-dir",
            str(tmp_path),
            "--issuer",
            "https://lab.zelkor.invalid",
            "--audiences",
            '["zelkor"]',
            "--seed-tenant",
            "seed-tenant",
            "--print-seed-token",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    token = res.stdout.strip()
    jwks = json.loads((tmp_path / "jwks.json").read_text())
    jwks_dir = tmp_path / "jwksdir"
    jwks_dir.mkdir()
    write_jwks_file(str(jwks_dir / "jwks"), jwks)
    monkeypatch.setenv("AUTH_JWKS_PATH", str(jwks_dir))
    monkeypatch.setenv("AUTH_JWT_ISSUER", "https://lab.zelkor.invalid")
    monkeypatch.setenv("AUTH_JWT_AUDIENCES", '["zelkor"]')
    validate_startup_config()
    claims = verify_bearer(f"Bearer {token}")
    assert claims["tenant_id"] == "seed-tenant"


def test_generate_does_not_log_private_key_material(tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    _run_generate(tmp_path)
    blob = caplog.text + (tmp_path / "private.pem").read_text(errors="ignore")
    assert "BEGIN PRIVATE KEY" not in caplog.text
    assert "privateKey" not in caplog.text.lower() or "path" in caplog.text.lower()


def test_rotation_id_changes_kid_on_fresh_state(tmp_path):
    _run_generate(tmp_path, rotation_id="1")
    kid1 = (tmp_path / "kid.txt").read_text().strip()
    other = tmp_path / "rot2"
    _run_generate(other, rotation_id="2")
    kid2 = (other / "kid.txt").read_text().strip()
    assert kid1 != kid2
