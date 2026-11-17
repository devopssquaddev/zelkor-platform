"""Offline: which Langfuse observations count as unexpected errors after a live run."""
from __future__ import annotations

from tests.helpers.langfuse import unexpected_error_observations


def _ids(rows):
    return [o["id"] for o in unexpected_error_observations(rows)]


def test_error_level_is_flagged():
    assert _ids([{"id": "a", "type": "SPAN", "name": "x", "level": "ERROR"}]) == ["a"]


def test_exception_in_output_or_status_is_flagged():
    rows = [
        {"id": "a", "type": "SPAN", "name": "x", "level": "DEFAULT", "output": "Traceback (most recent call last)"},
        {"id": "b", "type": "SPAN", "name": "y", "level": "DEFAULT", "statusMessage": "RuntimeException: boom"},
    ]
    assert _ids(rows) == ["a", "b"]


def test_prompt_mentioning_exception_is_not_flagged():
    """Agent system prompts may contain the word (OpenCode: "Exception: If working within ...")."""
    rows = [{"id": "a", "type": "GENERATION", "name": "general gpt-oss:20b", "level": "DEFAULT",
             "input": "Vary themes.\n\nException: If working within an existing design system, keep it.",
             "output": {"content": "sandbox-ok"}}]
    assert _ids(rows) == []


def test_failed_tool_output_is_flagged():
    rows = [{"id": "a", "type": "TOOL", "name": "sandbox__execute_python", "level": "DEFAULT",
             "output": "McpError: worker unavailable"}]
    assert _ids(rows) == ["a"]


def test_guardrail_refusal_is_not_flagged():
    rows = [{"id": "a", "type": "SPAN", "name": "rail", "level": "ERROR", "output": "request blocked by content_safety"}]
    assert _ids(rows) == []


def test_log_mode_self_check_without_verdict_is_known():
    meta = {"guardrail_mode": "log", "guardrail_status": "timeout"}
    rows = [
        {"id": "a", "type": "GENERATION", "name": "self_check_input gpt-oss:20b", "level": "ERROR",
         "statusMessage": "self-check timeout; request allowed", "metadata": meta},
        {"id": "b", "type": "SPAN", "name": "guardrail self_check input", "level": "ERROR",
         "statusMessage": "self-check error; request allowed",
         "metadata": {"guardrail_mode": "log", "guardrail_status": "error"}},
        {"id": "c", "type": "SPAN", "name": "guardrail self_check input", "level": "ERROR",
         "statusMessage": "self-check timeout; request allowed",
         "metadata": {"guardrail_mode": "block", "guardrail_status": "timeout"}},
        {"id": "d", "type": "GENERATION", "name": "self_check_input gpt-oss:20b", "level": "ERROR",
         "statusMessage": "self-check unparseable; request allowed",
         "metadata": {"guardrail_mode": "log", "guardrail_status": "unparseable"}},
    ]
    assert _ids(rows) == ["b", "c"]
