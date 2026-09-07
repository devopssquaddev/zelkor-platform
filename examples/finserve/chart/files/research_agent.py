"""FinServe research — policy RAG (Mode B drop-in).

Customer-shaped LangChain create_agent + ChatOpenAI. Zelkor injects MCP tools
at graph load. Guardrails: platform NeMo intercept on default /v1. No NEMO_URL,
MCP client, or Langfuse SDK in this module.
"""
from __future__ import annotations

import os

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

from mcp_tools import MCP_INJECT_PREFIXES, single_mcp_tool

COLLECTION = os.getenv("QDRANT_COLLECTION", "finserve_policies")
MODEL = os.getenv("DEFAULT_LLM_MODEL", "gpt-oss:20b")

SYSTEM = f"""FinServe Research. qdrant__search_documents on `{COLLECTION}` only."""

_model = ChatOpenAI(model=MODEL, temperature=0)
graph = create_agent(
    _model,
    tools=[single_mcp_tool("qdrant__search_documents")],
    system_prompt=SYSTEM,
)
