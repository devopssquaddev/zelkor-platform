"""gVisor sandbox worker — executes Python in isolated subprocess with workspace reset."""
import hmac
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bootstrap_runner import parse_bootstrap_line  # noqa: E402
from execution_report import analyze_execution, log_sandbox_execution  # noqa: E402

logger = logging.getLogger("zelkor-sandbox-worker")

MAX_BODY_BYTES = int(os.getenv("SANDBOX_MAX_BODY_BYTES", "1048576"))
_RUNNER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bootstrap_runner.py")


class WorkerHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        logger.debug(fmt, *args)

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
        if not expected:
            logger.warning("sandbox worker /run rejected: SANDBOX_WORKER_TOKEN not configured")
            self._json(403, {"status": "error", "error": "unauthorized"})
            return

        got = (self.headers.get("X-Sandbox-Worker-Token") or "").strip()
        if not hmac.compare_digest(got, expected):
            logger.warning("sandbox worker unauthorized")
            self._json(403, {"status": "error", "error": "unauthorized"})
            return

        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            self._json(400, {"status": "error", "error": "invalid Content-Length"})
            return
        if length > MAX_BODY_BYTES:
            self._json(413, {"status": "error", "error": "request body too large"})
            return

        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            logger.warning("sandbox worker invalid json")
            self._json(400, {"status": "error", "error": "invalid json"})
            return

        code = payload.get("code") or ""
        timeout = int(payload.get("timeout") or 5)
        workdir = tempfile.mkdtemp(prefix="sandbox-")
        temp_path = os.path.join(workdir, "user_code.py")
        env = os.environ.copy()
        from execution_report import detect_code_probes  # noqa: E402

        static_probes = list(detect_code_probes(code))
        env["SANDBOX_STATIC_PROBES"] = json.dumps(static_probes)
        try:
            with open(temp_path, "w", encoding="utf-8") as handle:
                handle.write(code)
            py = shutil.which("python3") or shutil.which("python") or "python3"
            res = subprocess.run(
                [py, _RUNNER_PATH, temp_path],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=workdir,
                env=env,
            )
            bootstrap = parse_bootstrap_line(res.stderr) or {}
            user_stdout = str(bootstrap.get("user_stdout") or res.stdout)
            user_stderr = str(bootstrap.get("user_stderr") or "")
            exit_code = int(bootstrap.get("exit_code") if bootstrap.get("exit_code") is not None else res.returncode)
            report = analyze_execution(
                code,
                stdout=user_stdout,
                stderr=user_stderr,
                exit_code=exit_code,
                bootstrap=bootstrap or None,
            )
            response = {
                "status": "success" if report.outcome == "allowed" else "error",
                "stdout": user_stdout,
                "stderr": user_stderr,
                "exit_code": exit_code,
                "execution": report.to_execution_dict(),
            }
            self._json(200, response)
            log_sandbox_execution(logger, report)
        except subprocess.TimeoutExpired:
            report = analyze_execution(code, timed_out=True, exit_code=-1, stderr="timeout")
            log_sandbox_execution(logger, report)
            self._json(
                200,
                {
                    "status": "error",
                    "error": "execution timeout",
                    "stdout": "",
                    "stderr": "timeout",
                    "exit_code": -1,
                    "execution": report.to_execution_dict(),
                },
            )
        except Exception as exc:
            report = analyze_execution(code, error=str(exc), exit_code=-1, stderr=str(exc))
            log_sandbox_execution(logger, report)
            logger.exception("sandbox execute failed")
            self._json(
                200,
                {
                    "status": "error",
                    "error": str(exc),
                    "stdout": "",
                    "stderr": str(exc),
                    "exit_code": -1,
                    "execution": report.to_execution_dict(),
                },
            )
        finally:
            shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    from zelkor_logging import configure_logging

    configure_logging("zelkor-sandbox-worker")
    if not os.getenv("SANDBOX_WORKER_TOKEN", "").strip():
        logger.critical(
            "SANDBOX_WORKER_TOKEN is not set; /run will reject all requests until configured",
            extra={"component": "zelkor-sandbox-worker", "event": "startup"},
        )
    port = int(os.getenv("PORT", "8081"))
    logger.info("sandbox worker listening on 0.0.0.0:%s", port, extra={"event": "startup"})
    HTTPServer(("0.0.0.0", port), WorkerHandler).serve_forever()
