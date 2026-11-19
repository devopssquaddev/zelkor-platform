"""S-03 (P3) L3: with NeMo intercept on and NeMo down, an agent's /v1 completion fails closed
(5xx, no chat.completion). It never falls through to the provider. Restores NeMo's replicas."""
from __future__ import annotations

import json
import os
import time

import httpx
import pytest

from tests.helpers.gateway import is_chat_completion
from tests.helpers.kube import consumer_key, kubectl_run, platform_contract
from tests.helpers.llm import llm_model_or_skip

BASE = os.environ.get("GATEWAY_BASE_URL", "http://127.0.0.1:8088")
HOST = os.environ.get("AI_GATEWAY_IN_CLUSTER_HOST", "zelkor-platform-ai-gateway")
SELECTOR = "app.kubernetes.io/component=guardrails"


def _nemo() -> tuple[str, int]:
    r = kubectl_run(["get", "deploy", "-l", SELECTOR, "-o", "json"])
    items = json.loads(r.stdout or "{}").get("items") or [] if r.returncode == 0 else []
    if not items:
        pytest.skip("no NeMo guardrails Deployment (NeMo off)")
    d = items[0]
    return d["metadata"]["name"], int(d["spec"].get("replicas") or 1)


def _running() -> int:
    """NeMo pods that still exist: a Terminating pod keeps serving open connections."""
    r = kubectl_run(["get", "pods", "-l", SELECTOR, "-o", "json"])
    return len(json.loads(r.stdout or "{}").get("items") or [])


def _scale(name: str, n: int) -> None:
    r = kubectl_run(["scale", f"deploy/{name}", f"--replicas={n}"])
    assert r.returncode == 0, r.stderr


def test_s03_completion_fails_closed_while_nemo_is_down():
    if not os.environ.get("KUBECONTEXT"):
        pytest.skip("KUBECONTEXT not set")
    if platform_contract().get("GUARDRAILS_ENABLED", "true").lower() == "false":
        pytest.skip("NeMo off: /v1 does not pass through NeMo")
    key = consumer_key()
    if not key:
        pytest.skip("no AI Gateway consumer key (env or Secret)")
    model = llm_model_or_skip()
    name, replicas = _nemo()
    headers = {"Host": HOST, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = {"model": model, "messages": [{"role": "user", "content": "Say hello in one word."}], "max_tokens": 16}
    up = httpx.post(f"{BASE}/v1/chat/completions", headers=headers, json=payload, timeout=120.0)
    assert up.status_code == 200 and is_chat_completion(up.json()), f"positive control: {up.status_code} {up.text[:200]}"
    _scale(name, 0)
    try:
        deadline = time.monotonic() + 120
        while _running() and time.monotonic() < deadline:
            time.sleep(2)
        assert _running() == 0, "NeMo pods still present after 120 s"
        time.sleep(5)  # Envoy drops the endpoint
        down = httpx.post(f"{BASE}/v1/chat/completions", headers=headers, json=payload, timeout=60.0)
        assert down.status_code >= 500, f"NeMo down but /v1 answered {down.status_code}: {down.text[:200]}"
        try:
            body = down.json()
        except ValueError:
            body = {}
        assert not is_chat_completion(body), "a completion came back while NeMo was down"
    finally:
        _scale(name, replicas)
        kubectl_run(["rollout", "status", f"deploy/{name}", "--timeout=180s"], timeout=200)
