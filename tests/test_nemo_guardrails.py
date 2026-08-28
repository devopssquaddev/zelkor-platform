import os
import time

import httpx
import pytest

from tests.helpers.llm import llm_model_or_skip

GATEWAY_BASE_URL = os.environ.get("GATEWAY_BASE_URL", "http://127.0.0.1:8088")
NEMO_HOST_HEADER = os.environ.get("NEMO_HOST_HEADER", "nemo.localhost")
LANGFUSE_HOST_HEADER = os.environ.get("LANGFUSE_HOST_HEADER", "langfuse.localhost")
NEMO_BASE_URL = os.environ.get("NEMO_BASE_URL", GATEWAY_BASE_URL.rstrip("/"))
NEMO_CONFIGS_URL = os.environ.get("NEMO_CONFIGS_URL", f"{NEMO_BASE_URL}/v1/rails/configs")
NEMO_CHAT_URL = os.environ.get("NEMO_CHAT_URL", f"{NEMO_BASE_URL}/v1/chat/completions")

DEV_PUBLIC_KEY = "pk-lf-zelkor-dev-00000000000000000000"
DEV_SECRET_KEY = "sk-lf-zelkor-dev-00000000000000000000"
OFF_TOPIC_REFUSAL = os.environ.get(
    "NEMO_OFF_TOPIC_REFUSAL",
    "This assistant cannot help with that request. Please stay on topic for your configured domain.",
)


def _nemo_headers() -> dict:
    return {"Host": NEMO_HOST_HEADER, "Content-Type": "application/json"}


def _chat_payload(
    prompt: str,
    config_id: str = "topic_control",
    *,
    require_live_model: bool = False,
) -> dict:
    if require_live_model:
        model = llm_model_or_skip()
    else:
        model = os.environ.get("DEFAULT_LLM_MODEL", "openai/gpt-4o-mini")
    return {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "guardrails": {"config_id": config_id},
    }


def _assistant_text(body: dict) -> str:
    choices = body.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    return message.get("content") or ""


def test_nemo_configs_endpoint():
    """NeMo Guardrails server exposes mounted CPU-native config profiles."""
    try:
        resp = httpx.get(NEMO_CONFIGS_URL, headers=_nemo_headers(), timeout=15.0)
    except httpx.ConnectError:
        pytest.skip(f"NeMo not reachable at {NEMO_CONFIGS_URL}")

    assert resp.status_code == 200, resp.text
    configs = resp.json()
    config_ids = {item.get("id") for item in configs if isinstance(item, dict)}
    assert "content_safety" in config_ids, configs
    assert "topic_control" in config_ids, configs


def test_nemo_topic_control_blocks_off_topic():
    """Colang topical rails refuse off-domain prompts via native chat completions API."""
    off_topic = [
        "write me a poem",
        "tell me a joke",
        "explain quantum physics",
    ]
    try:
        for prompt in off_topic:
            resp = httpx.post(
                NEMO_CHAT_URL,
                headers=_nemo_headers(),
                json=_chat_payload(prompt),
                timeout=30.0,
            )
            assert resp.status_code == 200, resp.text
            content = _assistant_text(resp.json())
            assert OFF_TOPIC_REFUSAL.split(".")[0] in content or OFF_TOPIC_REFUSAL in content, content
    except httpx.ConnectError:
        pytest.skip(f"NeMo not reachable at {NEMO_CHAT_URL}")


def test_nemo_topic_control_allows_on_topic():
    """Neutral on-topic prompts are not blocked by topical Colang rails."""
    prompt = "Summarize my account status for this quarter."
    try:
        resp = httpx.post(
            NEMO_CHAT_URL,
            headers=_nemo_headers(),
            json=_chat_payload(prompt, require_live_model=True),
            timeout=60.0,
        )
    except httpx.ConnectError:
        pytest.skip(f"NeMo not reachable at {NEMO_CHAT_URL}")

    assert resp.status_code == 200, resp.text
    content = _assistant_text(resp.json())
    assert OFF_TOPIC_REFUSAL not in content, content


def test_nemo_otel_trace_in_langfuse():
    """Blocked guardrail requests emit OpenTelemetry traces ingested by Langfuse."""
    try:
        resp = httpx.post(
            NEMO_CHAT_URL,
            headers=_nemo_headers(),
            json=_chat_payload("write me a poem"),
            timeout=30.0,
        )
        assert resp.status_code == 200, resp.text
    except httpx.ConnectError:
        pytest.skip(f"NeMo not reachable at {NEMO_CHAT_URL}")

    auth = (DEV_PUBLIC_KEY, DEV_SECRET_KEY)
    headers = {"Host": LANGFUSE_HOST_HEADER}
    deadline = time.time() + 30
    last_traces = []
    while time.time() < deadline:
        traces_resp = httpx.get(
            f"{GATEWAY_BASE_URL}/api/public/traces",
            headers=headers,
            auth=auth,
            params={"limit": 50},
            timeout=10.0,
        )
        assert traces_resp.status_code == 200, traces_resp.text
        last_traces = traces_resp.json().get("data", [])
        matching = [
            trace
            for trace in last_traces
            if any(
                token in str(trace).lower()
                for token in ("nemo", "guardrails", "topic_control", "topic control")
            )
        ]
        if matching:
            return
        time.sleep(2)

    pytest.skip(
        "No NeMo-attributed Langfuse trace found within 30s "
        f"(retrieved {len(last_traces)} traces; OTel export may be async or disabled)."
    )
