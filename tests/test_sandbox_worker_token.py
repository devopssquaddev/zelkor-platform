"""Sandbox worker /run token (no cluster)."""
import json
import sys
import threading
from http.server import HTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp"))

from sandbox.worker import WorkerHandler  # noqa: E402


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
