"""CE-2 (requirements_zelkor_cli.md §4) live: `zelkor init` -> `dev` -> `run` -> `logs` -> `undeploy`
on the lab's kind cluster with an RS256 tenant token. The run streams events+updates with
X-Graph-ID (the CLI's contract, unit-tested in test_zelkor_cli.py) and must end without an error
event; undeploy removes the release. Needs docker + kind on the runner: ZELKOR_CE2_LIVE=1."""
from __future__ import annotations

import os
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

from tests.helpers.tokens import token_for

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(os.environ.get("ZELKOR_CE2_LIVE", "") != "1",
                                reason="ZELKOR_CE2_LIVE=1 required (docker + kind on the runner)")


def _zelkor(store: Path, *args: str, env: dict | None = None, timeout: int = 900) -> subprocess.CompletedProcess:
    exe = shutil.which("zelkor") or str(Path(os.sys.executable).parent / "zelkor")
    return subprocess.run([exe, "--store", str(store), "--env", "lab", "--chart", str(ROOT / "charts/zelkor-agent"),
                           "--platform-chart", str(ROOT / "charts/zelkor-platform"), *args],
                          capture_output=True, text=True, timeout=timeout, env={**os.environ, **(env or {})})


def test_ce2_init_dev_run_logs_undeploy(tmp_path):
    ctx = os.environ.get("KUBECONTEXT", "")
    if not ctx:
        pytest.skip("KUBECONTEXT not set")
    token = token_for("tenant-a")
    store, agent = tmp_path / "envs.yaml", tmp_path / f"ce2-{uuid.uuid4().hex[:6]}"
    ns = os.environ.get("ZELKOR_PLATFORM_NAMESPACE", "default")
    exe = shutil.which("zelkor") or str(Path(os.sys.executable).parent / "zelkor")
    add = subprocess.run([exe, "--store", str(store), "env", "add", "lab", "--kube-context", ctx, "--namespace", ns],
                         capture_output=True, text=True, timeout=60)
    assert add.returncode == 0, add.stderr
    init = _zelkor(store, "init", str(agent))
    assert init.returncode == 0, init.stderr[-500:]
    try:
        dev = _zelkor(store, "dev", str(agent))
        assert dev.returncode == 0, dev.stderr[-1500:]
        run = _zelkor(store, "run", str(agent), "--input", "Say ok", timeout=300,
                      env={"ZELKOR_AEGRA_URL": os.environ.get("GATEWAY_BASE_URL", "http://127.0.0.1:8088"),
                           "ZELKOR_AUTH_TOKEN": token})
        assert run.returncode == 0, (run.stdout[-800:], run.stderr[-800:])
        assert "updates" in run.stdout or "updates" in run.stderr, run.stdout[-500:]
        logs = _zelkor(store, "logs", str(agent), "--no-follow", "--tail", "20", timeout=120)
        assert logs.returncode == 0, logs.stderr[-500:]
    finally:
        down = _zelkor(store, "undeploy", str(agent), timeout=300)
    assert down.returncode == 0, down.stderr[-500:]
