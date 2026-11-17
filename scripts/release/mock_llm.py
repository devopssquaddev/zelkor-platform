#!/usr/bin/env python3
"""CE-19g test provider: a stdlib OpenAI-compatible server for the kind gates (never shipped).

POST .../chat/completions answers 200 with a canned completion, or HTTP 500 when the requested
model contains "fail" (the 100%-failure provider of the retry storm). GET /health -> 200.
Usage: mock_llm.py [--port 8000]
"""
from __future__ import annotations

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, status: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/").endswith("/models"):
            self._send(200, {"object": "list", "data": [{"id": "ok", "object": "model"},
                                                         {"id": "fail", "object": "model"}]})
        else:
            self._send(200, {"status": "ok"})

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        try:
            req = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            req = {}
        model = str(req.get("model", ""))
        if "fail" in model:
            self._send(500, {"error": {"message": "mock provider always fails", "type": "server_error"}})
            return
        self._send(200, {
            "id": "chatcmpl-mock", "object": "chat.completion", "created": int(time.time()), "model": model,
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": "pong"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        })

    def log_message(self, *_args) -> None:  # quiet: the gate counts requests on the client side
        return


def make_server(host: str, port: int) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), Handler)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    make_server(args.host, args.port).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
