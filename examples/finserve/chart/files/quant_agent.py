"""FinServe quant — sandbox projections (Mode B drop-in).

Customer-shaped LangChain create_agent + ChatOpenAI. Zelkor injects MCP tools
at graph load. Guardrails: platform NeMo intercept on default /v1. No NEMO_URL,
MCP client, or Langfuse SDK in this module.
"""
from __future__ import annotations

import os

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

from mcp_tools import MCP_INJECT_PREFIXES, single_mcp_tool

MODEL = os.getenv("DEFAULT_LLM_MODEL", "")

SYSTEM = """FinServe Quant. Use sandbox__execute_python only."""

_model = ChatOpenAI(model=MODEL, temperature=0)
graph = create_agent(
    _model,
    tools=[single_mcp_tool("sandbox__execute_python")],
    system_prompt=SYSTEM,
)
