"""requirements_install_download_phase.md acceptance, offline: the first-create disk guard, the
volume prune, and the default first-party tag. Each function is sourced out of
scripts/install-engine.sh with stubbed tools, as test_install_modes.py does for the footer.
The live boxes (download banner order, cold installs, full-on-fresh-kind refusal) are L3-KIND."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "scripts" / "install-engine.sh"
LOG_FNS = 'log() { echo "LOG $*"; }; log_warn() { echo "WARN $*"; }; die() { echo "DIE $*"; exit 3; }'


def _stub(tmp_path: Path, name: str, body: str) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    (bin_dir / name).write_text(f"#!/bin/sh\n{body}\n")
    (bin_dir / name).chmod(0o755)
    return bin_dir


def _run(fn: str, tmp_path: Path, bin_dir: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    script = f"""
{LOG_FNS}
source <(sed -n '/^{fn}()/,/^}}/p' "{ENGINE}")
{fn}
"""
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=False,
                          env={**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", **(env or {})})


def _df(free_gb: int) -> str:
    kb = free_gb * 1024 * 1024
    return f'echo "Filesystem 1024-blocks Used Available Capacity Mounted"; echo "/dev/x 999999999 1 {kb} 1% /var/lib/docker"'


@pytest.mark.parametrize("free_gb,need,dies", [(3, "8", True), (8, "8", False), (30, "8", False), (9, "12", True)])
def test_disk_guard_dies_below_install_min_free_gb(tmp_path, free_gb, need, dies):
    bin_dir = _stub(tmp_path, "df", _df(free_gb))
    r = _run("require_docker_free_gb", tmp_path, bin_dir, {"INSTALL_MIN_FREE_GB": need})
    assert (r.returncode == 3) is dies, r.stdout
    if dies:
        assert f"Need {need}Gi free" in r.stdout and "docker volume prune -f" in r.stdout


def test_disk_guard_warns_between_min_and_warn(tmp_path):
    r = _run("require_docker_free_gb", tmp_path, _stub(tmp_path, "df", _df(10)))
    assert r.returncode == 0 and "WARN Only 10Gi free" in r.stdout


def test_disk_guard_does_not_block_when_df_is_unreadable(tmp_path):
    r = _run("require_docker_free_gb", tmp_path, _stub(tmp_path, "df", "exit 1"))
    assert r.returncode == 0 and "Could not measure" in r.stdout


def test_first_create_prunes_unused_volumes_only(tmp_path):
    calls = tmp_path / "docker.calls"
    r = _run("reclaim_unused_docker", tmp_path, _stub(tmp_path, "docker", f'echo "$*" >> "{calls}"'))
    assert r.returncode == 0
    assert calls.read_text().split("\n")[0] == "volume prune -f"
    assert "builder" not in calls.read_text()  # build cache stays (lab-only prune)


def test_default_first_party_tag_is_chart_app_version():
    app = str(yaml.safe_load((ROOT / "charts/zelkor-platform/Chart.yaml").read_text())["appVersion"])
    r = subprocess.run(["bash", "-c", f'source "{ROOT}/scripts/lib/first-party-image-tag.sh"; zelkor_chart_app_version'],
                       capture_output=True, text=True, check=True, env={**os.environ, "ZELKOR_REPO_ROOT": str(ROOT)})
    assert r.stdout.strip() == app and app != "dev"
    assert 'IMAGE_TAG="${IMAGE_TAG:-$(zelkor_chart_app_version)}"' in ENGINE.read_text()
