"""Bootstrap runner subprocess tests (no cluster)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "mcp" / "sandbox" / "bootstrap_runner.py"

MKNOD_SNIPPET = """import os, stat
try:
    os.mknod('/tmp/fake_sda', stat.S_IFBLK | 0o660, os.makedev(8, 1))
    print('EXPLOIT')
except Exception as e:
    print(f'caught {type(e).__name__}')
"""


def _run_bootstrap(code: str, probes: list[str] | None = None) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        code_path = Path(tmp) / "user_code.py"
        code_path.write_text(code, encoding="utf-8")
        env = os.environ.copy()
        env["SANDBOX_STATIC_PROBES"] = json.dumps(
            probes if probes is not None else ["mknod_device"]
        )
        proc = subprocess.run(
            [sys.executable, str(RUNNER), str(code_path)],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        assert proc.stderr, proc.stdout
        for line in proc.stderr.splitlines():
            if line.startswith("ZELKOR_SANDBOX_RESULT "):
                return json.loads(line[len("ZELKOR_SANDBOX_RESULT ") :])
        raise AssertionError(f"no bootstrap envelope: stderr={proc.stderr!r}")


def test_bootstrap_mknod_emits_denied_or_exploit():
    payload = _run_bootstrap(MKNOD_SNIPPET, probes=["mknod_device"])
    assert payload["outcome"] in ("denied", "exploit", "completed")
    assert "mknod_device" in (payload.get("probe_results") or {})


def test_bootstrap_benign_print_completed():
    payload = _run_bootstrap("print('sandbox-ok')", probes=[])
    assert payload["outcome"] == "completed"
    assert "sandbox-ok" in payload.get("user_stdout", "")
