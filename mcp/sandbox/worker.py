"""gVisor sandbox worker — executes Python in isolated subprocess with workspace reset."""
import json
import os
import shutil
import subprocess
import tempfile
from http.server import BaseHTTPRequestHandler, HTTPServer


class WorkerHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _json(self, code: int, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/health", "/healthz"):
            self._json(200, {"status": "ok", "service": "mcp-sandbox-worker", "sandbox": "gvisor"})
            return
        self._json(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/run":
            self._json(404, {"error": "not found"})
            return

        expected = os.getenv("SANDBOX_WORKER_TOKEN", "").strip()
        if expected:
            got = (self.headers.get("X-Sandbox-Worker-Token") or "").strip()
            if got != expected:
                self._json(403, {"status": "error", "error": "unauthorized"})
                return

        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            self._json(400, {"status": "error", "error": "invalid json"})
            return

        code = payload.get("code") or ""
        timeout = int(payload.get("timeout") or 5)
        workdir = tempfile.mkdtemp(prefix="sandbox-")
        temp_path = os.path.join(workdir, "user_code.py")
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                f.write(code)
            res = subprocess.run(
                ["python", temp_path],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=workdir,
            )
            self._json(200, {
                "status": "success" if res.returncode == 0 else "error",
                "stdout": res.stdout,
                "stderr": res.stderr,
                "exit_code": res.returncode,
            })
        except subprocess.TimeoutExpired:
            self._json(200, {"status": "error", "error": "execution timeout", "stdout": "", "stderr": "timeout"})
        except Exception as exc:
            self._json(200, {"status": "error", "error": str(exc), "stdout": "", "stderr": str(exc)})
        finally:
            shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8081"))
    HTTPServer(("0.0.0.0", port), WorkerHandler).serve_forever()
