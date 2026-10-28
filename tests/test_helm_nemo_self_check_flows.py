"""Self-check rails must be able to block (P10). No cluster.

nemoguardrails 0.24 returns a RailOutcome object from self_check_input/output. A Colang 1.0 flow
that tests it as a boolean (`if not $allowed`) never blocks, because the object is always truthy;
the harmful prompt then reached the main model and only the model's own training refused it.
"""
from __future__ import annotations

import re

from tests.test_helm_ai_gateway_providers import _docs, _helm, _named

OLLAMA = ("--set", "workspace.models.providers.ollamaCloud.apiKey=ollama-key")


def _flows(*extra):
    cm = _named(_docs(_helm(*OLLAMA, *extra)), "ConfigMap", "zelkor-platform-nemo-config")
    return cm["data"]["content_safety-flows.co"]


def test_self_check_flows_branch_on_is_blocked():
    flows = _flows("--set", "workspace.policies.nemo.selfCheck.enabled=true")
    for rail in ("self check input", "self check output"):
        body = flows.split(f"define flow {rail}", 1)[1].split("\ndefine ", 1)[0]
        assert "$response.is_blocked" in body, rail
        assert not re.search(r"if not \$allowed", body), f"{rail} tests the RailOutcome as a boolean"


def test_refusal_message_is_the_configured_one():
    flows = _flows("--set", "workspace.policies.nemo.selfCheck.enabled=true",
                   "--set", "workspace.policies.nemo.safetyRefusal=Blocked by policy.")
    assert '"Blocked by policy."' in flows.split("define bot refuse to respond", 1)[1].split("\n\n", 1)[0]


def test_self_check_prompts_treat_the_text_as_data():
    """Instruction-following models answered the user's request instead of Yes/No (wrong verdicts)."""
    cm = _named(_docs(_helm(*OLLAMA, "--set", "workspace.policies.nemo.selfCheck.enabled=true")),
                "ConfigMap", "zelkor-platform-nemo-config")
    import yaml

    tasks = {p["task"]: p["content"] for p in yaml.safe_load(cm["data"]["content_safety-prompts.yml"])["prompts"]}
    assert "<message>\n{{ user_input }}\n</message>" in tasks["self_check_input"]
    assert "<response>\n{{ bot_response }}\n</response>" in tasks["self_check_output"]
    assert all("Answer with exactly one word, Yes or No." in c for c in tasks.values())
