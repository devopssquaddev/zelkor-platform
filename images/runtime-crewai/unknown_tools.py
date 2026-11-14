"""Fail a run when the model calls a tool the agent was not offered.

With no tools offered, crewai's LLM returns the model's raw tool calls and the executor makes
them the final answer with str(): the caller gets a ChatCompletionMessageFunctionToolCall repr
with HTTP 200. This happens when the gateway policy denies the agent's only tool, or the model
invents one. Raise instead; the error names the tool(s), never the arguments.
"""
from __future__ import annotations

import functools
import inspect
from typing import Any


class UnknownToolCall(RuntimeError):
    pass


def _name(call: Any) -> str | None:
    fn = call.get("function") if isinstance(call, dict) else getattr(call, "function", None)
    name = fn.get("name") if isinstance(fn, dict) else getattr(fn, "name", None)
    return name if isinstance(name, str) else None


def _check(result: Any, tools: Any) -> Any:
    if tools or not isinstance(result, list) or not result:
        return result
    names = [_name(c) for c in result]
    if all(names):
        raise UnknownToolCall(
            f"model called {', '.join(sorted(set(names)))}, which this agent does not have "
            "(no tools offered: denied by policy or not in its tool scope)"
        )
    return result


def _tools(args: tuple, kwargs: dict) -> Any:
    return kwargs.get("tools", args[1] if len(args) > 1 else None)


def guard(llm: Any) -> Any:
    """Wrap llm.call / llm.acall in place and return llm."""
    call, acall = llm.call, getattr(llm, "acall", None)

    @functools.wraps(call)
    def guarded_call(*args, **kwargs):
        return _check(call(*args, **kwargs), _tools(args, kwargs))

    object.__setattr__(llm, "call", guarded_call)
    if acall is not None and inspect.iscoroutinefunction(acall):
        @functools.wraps(acall)
        async def guarded_acall(*args, **kwargs):
            return _check(await acall(*args, **kwargs), _tools(args, kwargs))

        object.__setattr__(llm, "acall", guarded_acall)
    return llm
