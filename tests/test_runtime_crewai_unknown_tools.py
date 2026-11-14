"""CrewAI runtime: a tool call for a tool the agent does not have fails the run.

With no tools offered, crewai's LLM returns the model's raw tool calls and the executor turns
them into the final answer with str() (HTTP 200, a ChatCompletionMessageFunctionToolCall
repr). The runtime raises instead, naming the tool, never its arguments.
"""
from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "images" / "runtime-crewai"))

import unknown_tools  # noqa: E402

CALL = types.SimpleNamespace(id="call_1", type="function",
                             function=types.SimpleNamespace(name="aigateway__call", arguments='{"secret": "x"}'))
DICT_CALL = {"id": "call_2", "type": "function", "function": {"name": "crm__search", "arguments": "{}"}}


class FakeLLM:
    def __init__(self, out):
        self.out = out

    def call(self, messages, tools=None, **kwargs):
        return self.out

    async def acall(self, messages, tools=None, **kwargs):
        return self.out


def test_tool_call_without_offered_tools_fails_naming_the_tool():
    llm = unknown_tools.guard(FakeLLM([CALL]))
    with pytest.raises(unknown_tools.UnknownToolCall) as exc:
        llm.call([{"role": "user", "content": "hi"}])
    assert "aigateway__call" in str(exc.value) and "secret" not in str(exc.value)


def test_async_path_and_dict_calls():
    llm = unknown_tools.guard(FakeLLM([DICT_CALL]))
    with pytest.raises(unknown_tools.UnknownToolCall, match="crm__search"):
        asyncio.run(llm.acall([], tools=[]))


def test_tool_calls_with_offered_tools_pass_through():
    llm = unknown_tools.guard(FakeLLM([CALL]))
    tools = [{"type": "function", "function": {"name": "aigateway__call"}}]
    assert llm.call([], tools=tools) == [CALL]
    assert asyncio.run(llm.acall([], tools)) == [CALL]


def test_text_answers_pass_through():
    llm = unknown_tools.guard(FakeLLM("pong"))
    assert llm.call([]) == "pong"
    assert asyncio.run(llm.acall([])) == "pong"
