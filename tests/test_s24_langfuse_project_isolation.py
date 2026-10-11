"""S-24 / P1+P11: team A Langfuse keys must not list team B / init runs."""
from __future__ import annotations

import os
import time
import uuid

import httpx
import pytest

from tests.helpers.langfuse import GATEWAY_BASE_URL, langfuse_auth, langfuse_headers, list_traces
from tests.helpers.llm import llm_model_or_skip


def _extra_auth() -> tuple[str, str]:
    pk = os.environ.get("LANGFUSE_EXTRA_PUBLIC_KEY", "").strip()
    sk = os.environ.get("LANGFUSE_EXTRA_SECRET_KEY", "").strip()
    if not pk or not sk:
        pytest.skip("LANGFUSE_EXTRA_PUBLIC_KEY / LANGFUSE_EXTRA_SECRET_KEY not set")
    return pk, sk


def _seed_init_trace() -> str:
    model = llm_model_or_skip()
    marker = f"s24-{uuid.uuid4().hex[:12]}"
    host = os.environ.get("AI_GATEWAY_IN_CLUSTER_HOST") or os.environ.get(
        "AI_GATEWAY_HOST_HEADER", "zelkor-platform-ai-gateway"
    )
    key = os.environ.get("AI_GATEWAY_API_KEY", os.environ.get("ZELKOR_CONSUMER_KEY", ""))
    headers = {
        "Host": host,
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}",
        "X-Tenant-ID": "tenant-a",
    }
    try:
        resp = httpx.post(
            f"{GATEWAY_BASE_URL}/v1/chat/completions",
            headers=headers,
            json={
                "model": model,
                "messages": [{"role": "user", "content": f"Reply with the token {marker} only."}],
                "max_tokens": 32,
                "temperature": 0,
            },
            timeout=120.0,
        )
    except httpx.ConnectError:
        pytest.skip(f"AI Gateway not reachable at {GATEWAY_BASE_URL}")
    if resp.status_code != 200:
        pytest.skip(f"chat/completions {resp.status_code}: {resp.text[:200]}")
    deadline = time.time() + 45
    while time.time() < deadline:
        traces = list_traces(limit=50, auth=langfuse_auth())
        if traces:
            return traces[0]["id"]
        time.sleep(2)
    pytest.skip("no init-project Langfuse traces after chat/completions")


def test_s24_extra_project_keys_do_not_list_init_run():
    if not os.environ.get("GATEWAY_BASE_URL"):
        pytest.skip("GATEWAY_BASE_URL not set")
    extra = _extra_auth()
    init_pk, _ = langfuse_auth()
    if extra[0] == init_pk:
        pytest.skip("extra Langfuse keys match init keys")
    init_id = _seed_init_trace()
    extra_traces = list_traces(limit=50, auth=extra)
    extra_ids = {t.get("id") for t in extra_traces}
    assert init_id not in extra_ids, (
        f"team A keys listed init/team B run {init_id}; Host={langfuse_headers()!r}"
    )
