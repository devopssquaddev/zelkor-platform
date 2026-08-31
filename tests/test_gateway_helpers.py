"""Unit tests for gateway/NeMo response helpers (no cluster)."""

from tests.helpers.gateway import (
    assistant_text,
    is_chat_completion,
    looks_like_refusal,
)


def test_is_chat_completion_accepts_empty_content():
    body = {
        "choices": [{"message": {"role": "assistant", "content": ""}}],
        "guardrails": {"config_id": "content_safety"},
    }
    assert is_chat_completion(body)
    assert assistant_text(body) == ""


def test_looks_like_refusal_covers_model_wording():
    assert looks_like_refusal("I’m sorry, but I can’t help with that.")
    assert looks_like_refusal("I can't help with that request.")
    assert not looks_like_refusal("Hello! How can I help you today?")
