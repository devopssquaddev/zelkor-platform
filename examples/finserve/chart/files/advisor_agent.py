"""FinServe advisor — portfolio SQL + synthesis (Mode B drop-in).

Customer-shaped LangChain create_agent + ChatOpenAI. Zelkor injects MCP tools
at graph load. Guardrails: platform NeMo intercept on default /v1. No NEMO_URL,
MCP client, or Langfuse SDK in this module.
"""
from __future__ import annotations

import os

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

MODEL = os.getenv("DEFAULT_LLM_MODEL", "gpt-oss:20b")

SYSTEM = """You are FinServe Advisor, a wealth-management assistant for the authenticated tenant.

Use only the tools bound on this graph (the platform injects them). Prefer:
- postgres__list_tables and postgres__get_schema to discover relations
- postgres__query for read-only SQL; always scope by the authenticated tenant_id

Do not invent table names. Do not return other tenants' data.
If a tool is unavailable, say so rather than fabricating holdings.
"""

_model = ChatOpenAI(model=MODEL, temperature=0)
graph = create_agent(_model, tools=[], system_prompt=SYSTEM)
