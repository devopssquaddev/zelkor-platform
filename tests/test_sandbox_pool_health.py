"""Unit tests for sandbox pool manager health (no cluster)."""
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp"))

from sandbox import pool_manager  # noqa: E402


def test_workers_healthy_false_when_all_probes_fail(monkeypatch):
    monkeypatch.setattr(pool_manager, "WORKER_URLS", ["http://worker-0:8081", "http://worker-1:8081"])
    with patch("urllib.request.urlopen", side_effect=OSError("connection refused")):
        assert pool_manager.workers_healthy() is False


def test_workers_healthy_false_when_no_workers_configured(monkeypatch):
    monkeypatch.setattr(pool_manager, "WORKER_URLS", [])
    assert pool_manager.workers_healthy() is False


def test_workers_healthy_true_when_one_probe_succeeds(monkeypatch):
    monkeypatch.setattr(pool_manager, "WORKER_URLS", ["http://worker-0:8081"])

    class _Resp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    with patch("urllib.request.urlopen", return_value=_Resp()):
        assert pool_manager.workers_healthy() is True
