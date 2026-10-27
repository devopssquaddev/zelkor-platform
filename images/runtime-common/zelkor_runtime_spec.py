"""Shared deploy-first agent spec for sidecar runtimes (agent.json + AGENTS.md).

Same rules as the Deep Agents factory: ``DEFAULT_LLM_MODEL`` wins over ``agent.json``;
a ``provider:`` prefix is dropped (the AI Gateway routes by model id). The runtime's LLM
and MCP endpoints are the sidecar loopback URLs from ``OPENAI_BASE_URL`` / ``MCP_URL``;
the runtime never holds a provider key or a tenant credential.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

APP = Path(os.getenv("ZELKOR_AGENT_DIR", "/app"))


@dataclass
class AgentSpec:
    name: str
    model: str
    instructions: str
    llm_base_url: str
    mcp_url: str


PROVIDER_PREFIXES = ("openai", "anthropic", "google", "google-genai", "azure", "azure_openai", "bedrock",
                     "vertex", "vertexai", "cohere", "groq", "mistral", "ollama")


def _strip_provider(raw: str) -> str:
    """``openai:gpt-4o`` → ``gpt-4o``; gateway ids like ``gpt-oss:20b`` stay intact."""
    raw = raw.strip()
    head, sep, rest = raw.partition(":")
    return rest.strip() if sep and head.lower() in PROVIDER_PREFIXES and rest.strip() else raw


def _model(agent: Dict[str, Any]) -> str:
    env_default = (os.getenv("DEFAULT_LLM_MODEL") or "").strip()
    raw: Any = agent.get("model")
    if isinstance(raw, dict):
        raw = raw.get("model_id") or raw.get("model") or ""
    model = env_default or _strip_provider(str(raw or ""))
    if not model:
        raise RuntimeError("no model: set DEFAULT_LLM_MODEL or agent.json \"model\"")
    return model


def load_spec(root: Path = APP) -> AgentSpec:
    agent_path = root / "agent.json"
    agent = json.loads(agent_path.read_text(encoding="utf-8")) if agent_path.is_file() else {}
    if not isinstance(agent, dict):
        agent = {}
    agents_md = root / "AGENTS.md"
    instructions = agents_md.read_text(encoding="utf-8") if agents_md.is_file() else ""
    llm = os.getenv("OPENAI_BASE_URL", "").strip().rstrip("/")
    mcp = os.getenv("MCP_URL", "").strip().rstrip("/")
    if not llm or not mcp:
        raise RuntimeError("OPENAI_BASE_URL and MCP_URL must point at the zelkor-sidecar loopback")
    return AgentSpec(
        name=str(agent.get("name") or os.getenv("ZELKOR_GRAPH_ID") or "agent").strip(),
        model=_model(agent),
        instructions=instructions or str(agent.get("description") or ""),
        llm_base_url=llm,
        mcp_url=mcp,
    )
