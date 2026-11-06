"""Sandbox example: private package math, image contract, pool image render."""
from __future__ import annotations

import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "examples" / "sandbox-python" / "desk_risk" / "src"
sys.path.insert(0, str(PKG))

import desk_risk  # noqa: E402

OVERLAY = ROOT / "examples" / "sandbox-python" / "values-platform-overlay.yaml"
DOCKERFILE = ROOT / "images" / "example-sandbox-python" / "Dockerfile"
REQS = ROOT / "images" / "example-sandbox-python" / "requirements.txt"
PYPROJECT = ROOT / "examples" / "sandbox-python" / "desk_risk" / "pyproject.toml"
IMAGE = "ghcr.io/devopssquaddev/zelkor-example-sandbox-python:2.4.2"

SECRET_SETS = [
    "postgresql.auth.password=test-pg",
    "clickhouse.auth.password=test-ch",
    "seaweedfs.auth.accessKey=test-ak",
    "seaweedfs.auth.secretKey=test-sk",
    "platform.telemetry.langfuse.nextauthSecret=test-na",
    "platform.telemetry.langfuse.salt=test-salt-1234567890",
    "platform.telemetry.langfuse.encryptionKey=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    "platform.telemetry.langfuse.nextauthUrl=https://langfuse.example.com",
    "platform.tenants.jwt.issuer=https://issuer.example",
    "platform.tenants.jwt.audiences[0]=zelkor",
    "platform.tenants.jwt.remoteJwksUri=https://issuer.example/.well-known/jwks.json",
    "platform.tenants.jwt.jwksEgressCIDRs[0]=203.0.113.0/24",
    "security.mcp.acceptUnprotectedBackends=true",
    "gateway.envoyProxy.enabled=true",
]


def test_herfindahl_splits_weights():
    assert desk_risk.herfindahl({"AAPL": 40, "MSFT": 30, "GOOGL": 30}) == pytest.approx(0.34)
    assert desk_risk.herfindahl({"AAPL": 100}) == pytest.approx(1.0)
    with pytest.raises(ValueError):
        desk_risk.herfindahl({})


def test_next_review_uses_dateutil():
    pytest.importorskip("dateutil")
    assert desk_risk.next_review(date(2026, 11, 5)) == date(2027, 11, 5)


def test_image_installs_private_package_and_pinned_wheels():
    dockerfile = DOCKERFILE.read_text()
    assert "ZELKOR_SANDBOX_WORKER_IMAGE" in dockerfile
    assert "pip install" in dockerfile
    assert "USER 1000" in dockerfile
    reqs = REQS.read_text()
    project = PYPROJECT.read_text()
    for pin in ("python-dateutil==4.0.0", "tzdata==2026.6"):
        assert pin in reqs
        assert pin in project
    build = (ROOT / "scripts" / "build-images.sh").read_text()
    assert "zelkor-example-sandbox-python" in build
    assert "ZELKOR_SANDBOX_WORKER_IMAGE" in build


def test_overlay_replaces_worker_image():
    cmd = [
        "helm",
        "template",
        "zelkor-platform",
        str(ROOT / "charts" / "zelkor-platform"),
        "--namespace",
        "zelkor",
        "-f",
        str(OVERLAY),
    ]
    for item in SECRET_SETS:
        cmd.extend(["--set", item])
    rendered = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert rendered.returncode == 0, rendered.stderr
    docs = [doc for doc in yaml.safe_load_all(rendered.stdout) if doc]
    workers = [
        doc
        for doc in docs
        if doc.get("kind") == "Deployment"
        and doc["metadata"]["name"].startswith("zelkor-platform-mcp-sandbox-worker-")
    ]
    assert len(workers) == 3
    for deploy in workers:
        image = deploy["spec"]["template"]["spec"]["containers"][0]["image"]
        assert image == IMAGE
