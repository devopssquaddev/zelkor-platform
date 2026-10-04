"""Aegra 0-arg factory: unmodified GPTR deep_agents; search via MCP tavily__*."""
from __future__ import annotations

import json
import os
import tempfile
import uuid
from typing import Any


def _gateway_model() -> str:
    raw = (os.getenv("STRATEGIC_LLM") or os.getenv("DEFAULT_LLM_MODEL") or "").strip()
    if not raw:
        return ""
    if raw.startswith("openai:"):
        return raw
    prefix, sep, rest = raw.partition("/")
    if sep and ":" not in prefix:
        return f"{prefix}:{rest}"
    if "/" not in raw:
        return f"openai:{raw}"
    return raw


def _pin_gateway_llms(model: str) -> None:
    for key in ("FAST_LLM", "SMART_LLM", "STRATEGIC_LLM"):
        os.environ[key] = model


_m = _gateway_model()
if _m:
    _pin_gateway_llms(_m)


def _search_call(query: str) -> tuple[str, dict[str, str]]:
    return "tavily__tavily_search", {"query": query}


def _research_call(query: str, parent_query: str = "") -> tuple[str, dict[str, str]]:
    q = query.strip()
    parent = parent_query.strip()
    if parent:
        q = f"{q} (overall topic: {parent})"
    return "tavily__tavily_research", {"input": q}


def graph() -> Any:
    from deep_agents.agent import CHIEF_EDITOR_PROMPT, RESEARCHER_PROMPT
    from deepagents import create_deep_agent
    from deepagents.backends import FilesystemBackend
    from langchain_core.tools import tool
    from mcp_inject import call_tool

    model = _gateway_model()
    if model:
        _pin_gateway_llms(model)

    @tool
    async def quick_search(query: str) -> str:
        """Fast web search: snippets and URLs. Use deep_research for cited reports."""
        return await call_tool(*_search_call(query))

    @tool
    async def deep_research(query: str, parent_query: str = "") -> str:
        """Thorough web research; returns cited markdown. parent_query is the overall topic."""
        return await call_tool(*_research_call(query, parent_query))

    @tool
    def write_todos(todos: list, max_per_page: int | None = None) -> str:
        """Record the research outline (section descriptions and target files)."""
        del max_per_page
        items = todos
        if isinstance(items, str):
            try:
                items = json.loads(items)
            except json.JSONDecodeError:
                items = [items]
        if isinstance(items, dict):
            items = items.get("todos") or items.get("items") or [items]
        path = os.path.join(run_dir, "todos.md")
        lines: list[str] = []
        for i, item in enumerate(items or [], 1):
            if isinstance(item, dict):
                desc = str(item.get("description") or item.get("title") or item)
                dest = str(item.get("file") or item.get("path") or "")
                lines.append(f"{i}. {desc}" + (f" → {dest}" if dest else ""))
            else:
                lines.append(f"{i}. {item}")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        return f"Wrote {len(lines)} todos to todos.md"

    run_dir = os.path.join(tempfile.gettempdir(), f"gptr-{uuid.uuid4().hex[:8]}")
    os.makedirs(run_dir, exist_ok=True)
    create: dict[str, Any] = {
        "tools": [quick_search, write_todos],
        "system_prompt": CHIEF_EDITOR_PROMPT.format(guidelines=""),
        "subagents": [
            {
                "name": "researcher",
                "description": (
                    "Citation-grade research on one section; writes a draft file. "
                    "Pass section topic, overall topic, and target path."
                ),
                "system_prompt": RESEARCHER_PROMPT,
                "tools": [quick_search, deep_research],
            }
        ],
        "backend": FilesystemBackend(root_dir=run_dir, virtual_mode=True),
    }
    if model:
        create["model"] = model
    compiled = create_deep_agent(**create)
    raw = os.getenv("ZELKOR_RECURSION_LIMIT", "80").strip()
    try:
        limit = max(25, int(raw))
    except ValueError:
        limit = 80
    return compiled.with_config({"recursion_limit": limit})
