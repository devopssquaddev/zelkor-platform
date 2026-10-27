"""Sandbox worker /run token (no cluster)."""
import json
import sys
import threading
from http.server import HTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp"))

from sandbox.worker import WorkerHandler  # noqa: E402


def test_worker_run_rejects_when_token_unset(monkeypatch):
    monkeypatch.delenv("SANDBOX_WORKER_TOKEN", raising=False)
    server = HTTPServer(("127.0.0.1", 0), WorkerHandler)
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        url = f"http://127.0.0.1:{port}/run"
        payload = json.dumps({"code": "print(1)", "timeout": 2}).encode()
        with pytest.raises(HTTPError) as exc_info:
            urlopen(Request(url, data=payload, method="POST"), timeout=3)
        assert exc_info.value.code == 403
        thread.join(timeout=5)
    finally:
        server.server_close()


def test_worker_run_requires_token_when_set(monkeypatch):
    monkeypatch.setenv("SANDBOX_WORKER_TOKEN", "s3cret")
    server = HTTPServer(("127.0.0.1", 0), WorkerHandler)
    thread = threading.Thread(target=lambda: (server.handle_request(), server.handle_request()), daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        url = f"http://127.0.0.1:{port}/run"
        payload = json.dumps({"code": "print(1)", "timeout": 2}).encode()
        try:
            urlopen(Request(url, data=payload, method="POST"), timeout=3)
            raise AssertionError("expected 403 without token")
        except HTTPError as exc:
            assert exc.code == 403
        req = Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json", "X-Sandbox-Worker-Token": "s3cret"},
            method="POST",
        )
        with urlopen(req, timeout=5) as resp:
            body = json.loads(resp.read().decode())
        assert body.get("exit_code") == 0
        assert "1" in (body.get("stdout") or "")
        thread.join(timeout=5)
    finally:
        server.server_close()


def test_worker_health_answers_during_a_long_run(monkeypatch):
    """Liveness must not fail while /run executes (worker was killed on runs > ~30 s)."""
    import time

    from sandbox.worker import make_server

    monkeypatch.setenv("SANDBOX_WORKER_TOKEN", "s3cret")
    server = make_server(0, host="127.0.0.1")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    try:
        payload = json.dumps({"code": "import time\ntime.sleep(3)\nprint(1)", "timeout": 10}).encode()
        run = Request(f"http://127.0.0.1:{port}/run", data=payload, method="POST",
                      headers={"X-Sandbox-Worker-Token": "s3cret", "Content-Type": "application/json"})
        result = {}
        runner = threading.Thread(target=lambda: result.setdefault("r", json.loads(urlopen(run, timeout=15).read())))
        runner.start()
        time.sleep(0.5)
        started = time.monotonic()
        with urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as resp:
            assert resp.status == 200
        assert time.monotonic() - started < 1.5
        runner.join(timeout=15)
        assert result["r"]["status"] == "success", result
    finally:
        server.shutdown()
        server.server_close()
