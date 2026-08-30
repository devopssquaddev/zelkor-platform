"""Unit tests for NeMo chat.completions body normalization."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "images" / "aegra"))

from openai_compat import normalize_chat_completion  # noqa: E402


def test_normalize_fills_null_choices_from_messages():
    body = {
        "id": "x",
        "choices": None,
        "messages": [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "I can't help with that request."},
        ],
    }
    out = normalize_chat_completion(body)
    assert out["choices"][0]["message"]["content"] == "I can't help with that request."


def test_normalize_keeps_existing_choices():
    body = {"choices": [{"message": {"role": "assistant", "content": "ok"}}]}
    assert normalize_chat_completion(body)["choices"][0]["message"]["content"] == "ok"


def test_rewrite_roundtrip_bytes():
    from openai_compat import _rewrite_bytes

    raw = json.dumps(
        {"choices": None, "messages": [{"role": "assistant", "content": "nope"}]}
    ).encode()
    out = json.loads(_rewrite_bytes(raw))
    assert out["choices"][0]["message"]["content"] == "nope"
