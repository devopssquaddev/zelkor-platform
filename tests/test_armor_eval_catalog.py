"""CE-12 evaluator functions. Skips when node is not installed."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parents[1] / "images" / "langfuse-seed" / "evaluators"
_NODE = shutil.which("node")


def _evaluate(filename: str, ctx: dict) -> dict:
    if not _NODE:
        pytest.skip("node is not installed")
    src = (_DIR / filename).read_text(encoding="utf-8")
    script = (
        "const src = "
        + json.dumps(src)
        + ";\n"
        + "const evaluate = new Function('ctx', src + '\\nreturn evaluate(ctx);');\n"
        + "process.stdout.write(JSON.stringify(evaluate("
        + json.dumps(ctx)
        + ")));\n"
    )
    proc = subprocess.run([_NODE, "-e", script], capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _value(result: dict) -> bool:
    return bool(result["scores"][0]["value"])


def test_refusal_empty_output_is_not_a_fail():
    result = _evaluate("refusal.ts", {"observation": {"output": ""}})
    assert _value(result) is True
    assert "not captured" in result["scores"][0]["comment"]


def test_refusal_heuristic_passes_and_plain_text_fails():
    assert _value(_evaluate("refusal.ts", {"observation": {"output": "I can't help with that"}})) is True
    assert _value(_evaluate("refusal.ts", {"observation": {"output": "Your balance is 10"}})) is False


def test_mcp_prefix_and_repeat_and_sandbox():
    assert _value(_evaluate("mcp_prefix.ts", {"observation": {"metadata": {"tool_name": "postgres__query"}}})) is True
    assert _value(_evaluate("mcp_prefix.ts", {"observation": {"metadata": {"tool_name": "search"}}})) is False
    assert _value(_evaluate("tool_repeat.ts", {"observation": {"metadata": {"tool_repeat": "true"}}})) is False
    assert _value(_evaluate("tool_repeat.ts", {"observation": {"metadata": {}}})) is True
    dirty = _evaluate(
        "sandbox_clean.ts",
        {"observation": {"metadata": {"sandbox.violation": "egress"}}},
    )
    assert _value(dirty) is False
    assert _value(_evaluate("sandbox_clean.ts", {"observation": {"metadata": {}}})) is True


def test_tool_error_rule_scores_false():
    assert _value(_evaluate("tool_succeeded.ts", {"observation": {}})) is False


def test_root_tool_names_and_step_budget():
    names = json.dumps(["postgres__query", "sandbox__execute_python"])
    ctx = {"observation": {"metadata": {"tool_names": names, "user_id": "user-1"}}}
    assert _value(_evaluate("tool_names.ts", ctx)) is True
    assert _value(_evaluate("step_budget.ts", ctx)) is True
    assert _value(_evaluate("tenant.ts", ctx)) is True
    objects = {"observation": {"metadata": {"tool_names": json.dumps([{"name": "postgres__query", "arguments": {}}])}}}
    assert _value(_evaluate("tool_names.ts", objects)) is False
    long_list = json.dumps(["postgres__query"] * 26)
    assert _value(_evaluate("step_budget.ts", {"observation": {"metadata": {"tool_names": long_list}}})) is False
    assert _value(_evaluate("tenant.ts", {"observation": {"metadata": {}}})) is False
