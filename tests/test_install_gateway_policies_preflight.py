"""Installer preflight: Gateway listener ports are read without PyYAML.

The check compares the chart's Gateway listeners with zelkor-gateway-policies. It used to
import yaml; on a python3 without PyYAML it failed and the installer treated that as a pass.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "scripts" / "lib" / "gateway-policies.sh"
CHART = ROOT / "charts" / "zelkor-platform"
PROFILES = ROOT / "profiles"

pytestmark = pytest.mark.skipif(shutil.which("helm") is None, reason="helm not installed")


def _ports(tmp_path: Path, *sets: str) -> subprocess.CompletedProcess[str]:
    shim = tmp_path / "bin"
    shim.mkdir()
    # python3 without site-packages: no PyYAML, standard library only
    (shim / "python3").write_text(f'#!/bin/sh\nexec "{sys.executable}" -I -S "$@"\n')
    (shim / "python3").chmod(0o755)
    jwks = tmp_path / "jwks.json"
    jwks.write_text(json.dumps({"keys": [{"kty": "RSA", "kid": "k", "n": "AQAB", "e": "AQAB"}]}))
    args = [
        "-f", str(PROFILES / "values-production.yaml"), "-f", str(PROFILES / "values-perimeter.yaml"),
        "-f", str(PROFILES / "values-gateway-layered.yaml"),
        "--set", "gateway.hosts.agents=agents.example.com",
        "--set", "platform.tenants.jwt.issuer=https://idp.example.com",
        "--set-string", "platform.tenants.jwt.audiences[0]=zelkor",
        "--set-file", f"platform.tenants.jwt.jwks={jwks}",
    ]
    for s in sets:
        args += ["--set", s]
    script = f'source "{LIB}"; gateway_policies_platform_listener_ports "$@"'
    return subprocess.run(
        ["bash", "-c", script, "_", str(CHART), "zelkor", "zelkor-platform", *args],
        capture_output=True, text=True, check=False,
        env={"PATH": f"{shim}:/usr/bin:/bin:{Path(shutil.which('helm')).parent}"},
    )


def test_listener_ports_without_pyyaml(tmp_path):
    r = _ports(tmp_path)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "80"
    assert "No module named" not in r.stderr


def test_listener_ports_with_tls(tmp_path):
    r = _ports(tmp_path, "gateway.tls.enabled=true", "gateway.tls.clusterIssuer=letsencrypt")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "80 443"
