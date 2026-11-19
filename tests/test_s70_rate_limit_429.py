"""S-70 (P15) L3: the install-wide /v1 cap answers 429 by call rpm+1 inside one minute, and an agent
gets that 429 while the bucket is spent (NeMo does not retry it: max_retries 0 in its config).

Only provider calls spend the bucket; with NeMo intercept that is the NeMo -> provider hop
(bypass header + model header). So the burst runs inside the NeMo container with NeMo's own key
(the key never leaves the pod); without NeMo the burst is plain consumer-key /v1 calls. The cap is
read from the release's BackendTrafficPolicy (ZELKOR_RATE_LIMIT_RPM overrides); a lab runs this
with a low cap. The test waits out the window afterwards so later tests are not throttled."""
from __future__ import annotations

import json
import os
import time

import httpx
import pytest

from tests.helpers.kube import consumer_key, kubectl_run, platform_contract
from tests.helpers.llm import llm_model_or_skip

BASE = os.environ.get("GATEWAY_BASE_URL", "http://127.0.0.1:8088")
HOST = os.environ.get("AI_GATEWAY_IN_CLUSTER_HOST", "zelkor-platform-ai-gateway")
RELEASE = os.environ.get("ZELKOR_PLATFORM_RELEASE", "zelkor-platform")
MAX_BURST = 400

BURST = """
import concurrent.futures as cf, json, os, sys, urllib.error, urllib.request
n, model = int(sys.argv[1]), sys.argv[2]
key, base = os.environ["OPENAI_API_KEY"], os.environ["MAIN_MODEL_BASE_URL"].rstrip("/")
body = json.dumps({"model": model, "messages": [{"role": "user", "content": "1"}], "max_tokens": 1}).encode()
hdr = {"Authorization": "Bearer " + key, "Content-Type": "application/json",
       "x-zelkor-guardrails-bypass": "1", "x-ai-eg-model": model}
def call(_):
    try:
        return urllib.request.urlopen(urllib.request.Request(base + "/chat/completions", data=body, headers=hdr),
                                      timeout=90).status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as e:
        return type(e).__name__
with cf.ThreadPoolExecutor(16) as pool:
    print(json.dumps(list(pool.map(call, range(n)))))
"""


def _cap() -> int:
    raw = os.environ.get("ZELKOR_RATE_LIMIT_RPM", "").strip()
    if raw:
        return int(raw)
    r = kubectl_run(["get", "backendtrafficpolicy", "-o", "json"])
    if r.returncode != 0:
        pytest.skip(r.stderr.strip()[:200])
    for p in json.loads(r.stdout).get("items") or []:
        for rule in (((p.get("spec") or {}).get("rateLimit") or {}).get("global") or {}).get("rules") or []:
            limit = rule.get("limit") or {}
            if str(limit.get("unit", "")).lower() == "minute" and limit.get("requests"):
                return int(limit["requests"])
    pytest.skip("no per-minute /v1 rate limit in this install (workspace.models.rateLimit off)")


def _burst_via_nemo(n: int, model: str) -> list:
    r = kubectl_run(["exec", f"deploy/{RELEASE}-nemo", "-c", "nemo-guardrails", "--", "python3", "-c", BURST,
                     str(n), model], timeout=300)
    assert r.returncode == 0, f"burst in NeMo failed: {r.stderr[-300:]}"
    return json.loads(r.stdout.strip().splitlines()[-1])


def _burst_direct(n: int, model: str, key: str) -> list:
    body = {"model": model, "messages": [{"role": "user", "content": "1"}], "max_tokens": 1}
    with httpx.Client(base_url=BASE, timeout=90.0,
                      headers={"Host": HOST, "Authorization": f"Bearer {key}"}) as c:
        return [c.post("/v1/chat/completions", json=body).status_code for _ in range(n)]


def test_s70_global_rpm_answers_429_by_call_rpm_plus_one():
    if not os.environ.get("KUBECONTEXT"):
        pytest.skip("KUBECONTEXT not set")
    rpm, key, model = _cap(), consumer_key(), llm_model_or_skip()
    if not key:
        pytest.skip("no AI Gateway consumer key")
    if rpm + 1 > MAX_BURST:
        pytest.skip(f"cap {rpm} is too high to burst with real calls in one minute; run with the lab low-cap overlay")
    intercept = platform_contract().get("GUARDRAILS_ENABLED", "true").lower() != "false"
    while time.time() % 60 > 20:  # start early in a window so the burst cannot straddle two
        time.sleep(1)
    t0 = time.monotonic()
    try:
        statuses = _burst_via_nemo(rpm + 1, model) if intercept else _burst_direct(rpm + 1, model, key)
        took = time.monotonic() - t0
        assert statuses.count(200) >= 1, f"no call got through: {statuses}"
        assert 429 in statuses, f"no 429 in {rpm + 1} calls ({took:.0f}s): {statuses}"
        if intercept:  # bucket spent: the agent gets NeMo's relay of the gateway 429, at once
            t1 = time.monotonic()
            agent = httpx.post(f"{BASE}/v1/chat/completions", timeout=90.0,
                               headers={"Host": HOST, "Authorization": f"Bearer {key}"},
                               json={"model": model, "messages": [{"role": "user", "content": "1"}], "max_tokens": 1})
            assert agent.status_code == 429, f"agent got {agent.status_code} while the bucket was spent: {agent.text[:200]}"
            assert time.monotonic() - t1 < 20, "the 429 was held back (retried inside NeMo)"
    finally:
        time.sleep(61 - time.time() % 60)  # let the bucket refill for the rest of the suite
