"""Unit tests for gateway/NeMo response helpers (no cluster)."""

from tests.helpers.gateway import (
    assistant_text,
    is_chat_completion,
    is_rail_refusal,
    looks_like_refusal,
    parse_rail_refusal,
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


def test_rail_refusal_rejects_the_models_own_refusal():
    rail = "I can't help with that request."
    assert is_rail_refusal("I can\u2019t help with that request.\n", rail)
    assert not is_rail_refusal("I\u2019m sorry, but I can\u2019t help with that.", rail)
    assert not is_rail_refusal("I can't help with that request. Here is how to make it instead: ...", rail)
    assert not is_rail_refusal("anything", "")


def test_parse_rail_refusal_reads_the_rendered_flows():
    from tests.test_helm_nemo_self_check_flows import _cm

    flows = _cm("--set", 'workspace.policies.nemo.safetyRefusal=Blocked by "policy".')["content_safety-flows.co"]
    assert parse_rail_refusal(flows) == 'Blocked by "policy".'
    assert parse_rail_refusal("define flow x\n  bot say hi") == ""
