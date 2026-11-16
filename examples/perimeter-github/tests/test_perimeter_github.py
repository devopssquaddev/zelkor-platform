"""perimeter-github example, offline: the platform overlay renders a GitHub relay that allows reads
only, and the agent's tools call the relay without any token."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import httpx
import yaml

from tests.test_helm_values_schema import _docs, _helm

EXAMPLE = Path(__file__).resolve().parents[1]
ROOT = EXAMPLE.parents[1]
sys.path.insert(0, str(EXAMPLE / "agent"))

import github_tools  # noqa: E402


def _relay_docs() -> list[dict]:
    r = _helm(values_files=[ROOT / "profiles" / "values-local-perimeter.yaml",
                            EXAMPLE / "values-platform-overlay.yaml"])
    assert r.returncode == 0, r.stderr
    return [d for d in _docs(r.stdout) if d and d["metadata"]["name"] == "zelkor-platform-api-github"]


def test_overlay_is_reads_only_with_the_token_from_a_secret():
    overlay = yaml.safe_load((EXAMPLE / "values-platform-overlay.yaml").read_text())
    (api,) = overlay["workspace"]["tools"]["httpApis"]
    assert api["credential"] == {"secretRef": "github-api"}
    assert {m for r in api["rules"] for m in r.get("methods", [])} == {"GET"}
    assert all(r["action"] == "Allow" for r in api["rules"])  # everything else: default deny


def test_overlay_renders_relay_with_default_deny():
    docs = _relay_docs()
    assert {d["kind"] for d in docs} == {"Service", "Backend", "HTTPRoute", "SecurityPolicy"}
    sp = next(d for d in docs if d["kind"] == "SecurityPolicy")
    assert sp["spec"]["authorization"]["defaultAction"] == "Deny"
    assert all('request.method in ["GET"]' in r["cel"] for r in sp["spec"]["authorization"]["rules"])


class _Recorder:
    def __init__(self, status=200, body=None):
        self.requests: list[httpx.Request] = []
        self.status, self.body = status, body if body is not None else []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(self.status, json=self.body)


def _call(rec, coro_fn, *args, monkeypatch):
    monkeypatch.setenv("ZELKOR_API_GITHUB_URL", "http://127.0.0.1:8001/run/active/api/github")
    monkeypatch.setattr(github_tools, "_transport", httpx.MockTransport(rec))
    return asyncio.run(coro_fn(*args))


def test_read_calls_the_relay_with_no_token(monkeypatch):
    rec = _Recorder(body=[{"number": 7, "title": "Bug", "state": "open", "created_at": "2011-01-26T19:01:12Z",
                           "html_url": "https://github.com/o/r/issues/7", "body": "x" * 5000,
                           "user": {"login": "a"}, "labels": [{"name": "bug"}]}])
    out = _call(rec, github_tools.github_read, "/repos/o/r/issues?state=open", monkeypatch=monkeypatch)
    (req,) = rec.requests
    assert str(req.url) == "http://127.0.0.1:8001/run/active/api/github/repos/o/r/issues?state=open"
    assert req.method == "GET" and "authorization" not in req.headers
    # issue lists are slimmed so the model sees the fields it needs, not 5 KB bodies
    assert json.loads(out) == [{"number": 7, "title": "Bug", "state": "open", "created_at": "2011-01-26T19:01:12Z",
                                "html_url": "https://github.com/o/r/issues/7", "labels": ["bug"]}]


def test_write_denied_by_the_gateway_is_reported_not_raised(monkeypatch):
    rec = _Recorder(status=403, body={"message": "RBAC: access denied"})
    out = _call(rec, github_tools.github_write, "patch", "/repos/o/r/issues/1", {"state": "closed"},
                monkeypatch=monkeypatch)
    (req,) = rec.requests
    assert req.method == "PATCH" and json.loads(req.content) == {"state": "closed"}
    assert out.startswith("HTTP 403") and "not permitted" in out


def test_missing_relay_url_is_a_clear_error(monkeypatch):
    monkeypatch.delenv("ZELKOR_API_GITHUB_URL", raising=False)
    out = asyncio.run(github_tools.github_read("/repos/o/r"))
    assert "ZELKOR_API_GITHUB_URL" in out
