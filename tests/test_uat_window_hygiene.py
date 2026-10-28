"""UAT window hygiene: no unexpected ERROR traces or ERROR logs since the run started (live).

Run last in a UAT session with ZELKOR_UAT_WINDOW_START (ISO-8601 UTC). Guardrail refusals and
Langfuse code-evaluator rows are expected. Anything else at ERROR fails; allow a known line with
ZELKOR_UAT_LOG_ALLOW (comma-separated regexes) and say why in the handoff.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re

import pytest

from tests.helpers.kube import kubectl_run
from tests.helpers.langfuse import is_code_eval_observation, langfuse_get
from tests.helpers.runtime_agents import require_kube

ERROR_LINE = re.compile(r'"level": ?"(ERROR|CRITICAL)"|^Traceback \(most recent call last\)|\blevel=error\b')
REFUSAL = re.compile(r"can't help|cannot help|can’t help|i'm sorry|guardrail|content_safety|blocked", re.I)


def _start() -> dt.datetime:
    raw = os.environ.get("ZELKOR_UAT_WINDOW_START", "").strip()
    if not raw:
        pytest.skip("ZELKOR_UAT_WINDOW_START not set")
    return dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))


def _allow() -> list[re.Pattern]:
    return [re.compile(p) for p in os.environ.get("ZELKOR_UAT_LOG_ALLOW", "").split(",") if p.strip()]


def test_no_unexpected_error_observations_in_the_window():
    start = _start()
    bad = []
    for page in range(1, 60):
        resp = langfuse_get("/api/public/v2/observations", params={
            "fromStartTime": start.strftime("%Y-%m-%dT%H:%M:%SZ"), "limit": 80, "page": page,
            "fields": "core,basic,io"})
        assert resp.status_code == 200, resp.text[:200]
        rows = resp.json().get("data") or []
        for o in rows:
            if str(o.get("level")).upper() != "ERROR" or is_code_eval_observation(o):
                continue
            blob = json.dumps([o.get("statusMessage"), o.get("output")])[:2000]
            if REFUSAL.search(blob):
                continue
            bad.append((o.get("traceId"), o.get("name"), str(o.get("statusMessage"))[:120]))
        if len(rows) < 80:
            break
    assert not bad, bad[:10]


def test_no_unexpected_error_logs_in_the_window():
    require_kube()
    since = int((dt.datetime.now(dt.timezone.utc) - _start()).total_seconds()) + 60
    allow = _allow()
    pods = json.loads(kubectl_run(["get", "pods", "-o", "json"]).stdout)["items"]
    bad = {}
    for pod in pods:
        spec = pod["spec"]
        for c in (spec.get("initContainers") or []) + spec["containers"]:
            out = kubectl_run(["logs", pod["metadata"]["name"], "-c", c["name"], f"--since={since}s"], timeout=60).stdout
            lines = [l for l in out.splitlines() if ERROR_LINE.search(l) and not any(a.search(l) for a in allow)]
            if lines:
                bad[f"{pod['metadata']['name']}/{c['name']}"] = lines[0][:200]
    assert not bad, bad
