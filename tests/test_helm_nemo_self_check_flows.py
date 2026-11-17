"""Self-check rails: input logs by default, output is off, either can be set to block. No cluster.

The default used to block on both sides. The self-check model's free-text Yes/No answer was
model-dependent, and NeMo's keyword parser treats an unclear answer as a block, so the default
install refused ordinary requests. The flows now call zelkor_self_check, which asks for JSON and
lets the request through (and logs) when the answer is unclear or slow.
"""
from __future__ import annotations

import yaml

from tests.test_helm_ai_gateway_providers import _docs, _helm, _named

OLLAMA = ("--set", "workspace.models.providers.ollamaCloud.apiKey=ollama-key")


def _cm(*extra):
    return _named(_docs(_helm(*OLLAMA, *extra)), "ConfigMap", "zelkor-platform-nemo-config")["data"]


def _flow(flows: str, name: str) -> str:
    return flows.split(f"define flow {name}", 1)[1].split("\ndefine ", 1)[0]


def _rails(data) -> dict:
    return yaml.safe_load(data["content_safety-config.yml"])["rails"]


def test_default_input_logs_and_output_is_off():
    data = _cm()
    assert _rails(data)["input"]["flows"] == ["self check input"]
    assert _rails(data)["output"].get("flows") == []
    body = _flow(data["content_safety-flows.co"], "self check input")
    assert 'execute zelkor_self_check(side="input", mode="log", timeout_ms=1500)' in body
    assert "$verdict.blocked" in body
    assert "define flow self check output" not in data["content_safety-flows.co"]


def test_block_mode_on_both_sides():
    data = _cm("--set", "workspace.policies.nemo.selfCheck.input=block",
               "--set", "workspace.policies.nemo.selfCheck.output=block",
               "--set", "workspace.policies.nemo.selfCheck.timeoutMs=3000")
    flows = data["content_safety-flows.co"]
    assert 'side="input", mode="block", timeout_ms=3000' in _flow(flows, "self check input")
    assert 'side="output", mode="block", timeout_ms=3000' in _flow(flows, "self check output")
    assert _rails(data)["output"]["flows"] == ["self check output"]


def test_none_omits_the_rail_and_its_model():
    data = _cm("--set", "workspace.policies.nemo.selfCheck.input=none")
    assert _rails(data)["input"]["flows"] == []
    models = {m["type"] for m in yaml.safe_load(data["content_safety-config.yml"])["models"]}
    assert models == {"main"}


def test_disabled_self_check_omits_both_rails():
    data = _cm("--set", "workspace.policies.nemo.selfCheck.enabled=false",
               "--set", "workspace.policies.nemo.selfCheck.output=block")
    assert _rails(data)["input"]["flows"] == []
    assert _rails(data)["output"]["flows"] == []


def test_invalid_mode_fails_render():
    err = _helm(*OLLAMA, "--set", "workspace.policies.nemo.selfCheck.input=shadow", check=False)
    assert "selfCheck.input" in err and '"log", "block", "none"' in err


def test_refusal_message_is_the_configured_one():
    flows = _cm("--set", "workspace.policies.nemo.safetyRefusal=Blocked by policy.")["content_safety-flows.co"]
    assert '"Blocked by policy."' in flows.split("define bot refuse to respond", 1)[1].split("\n\n", 1)[0]


def test_self_check_prompts_treat_the_text_as_data_and_ask_for_json():
    """Instruction-following models answered the user's request instead of a verdict."""
    data = _cm()
    tasks = {p["task"]: p["content"] for p in yaml.safe_load(data["content_safety-prompts.yml"])["prompts"]}
    assert "<message>\n{{ user_input }}\n</message>" in tasks["self_check_input"]
    assert "<response>\n{{ bot_response }}\n</response>" in tasks["self_check_output"]
    assert all('{"block": true}' in c and '{"block": false}' in c for c in tasks.values())
