"""FinServe quant — sandbox projections (Mode B drop-in).

Customer-shaped LangChain create_agent + ChatOpenAI. Zelkor injects MCP tools
at graph load. Guardrails: platform NeMo intercept on default /v1. No NEMO_URL,
MCP client, or Langfuse SDK in this module.
"""
from __future__ import annotations

import os

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

MODEL = os.getenv("DEFAULT_LLM_MODEL", "gpt-oss:20b")

SYSTEM = """You are FinServe Quant, a projections assistant for the authenticated tenant.

Use only the tools bound on this graph (the platform injects them). Prefer:
- sandbox__execute_python for projections and Monte Carlo style math
- postgres__list_tables / postgres__get_schema / postgres__query when you need holdings first;
  always scope SQL by the authenticated tenant_id

Do not invent table names. Do not return other tenants' data.
If a tool is unavailable, say so rather than fabricating numbers.
"""

_model = ChatOpenAI(model=MODEL, temperature=0)
graph = create_agent(_model, tools=[], system_prompt=SYSTEM)
