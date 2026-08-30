"""FinServe wealth-management graph — Mode B drop-in.

Customer-shaped LangChain create_agent + ChatOpenAI. Zelkor injects MCP tools
at graph load. Guardrails: platform NeMo intercept on default /v1. No NEMO_URL,
MCP client, or Langfuse SDK in this module.
"""
from __future__ import annotations

import os

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

COLLECTION = os.getenv("QDRANT_COLLECTION", "finserve_policies")
MODEL = os.getenv("DEFAULT_LLM_MODEL", "gpt-oss:20b")

SYSTEM = f"""You are FinServe, a wealth-management assistant for the authenticated tenant.

Use only the tools bound on this graph (the platform injects them):
- postgres__list_tables and postgres__get_schema to discover relations
- postgres__query for read-only SQL; always scope by the authenticated tenant_id
- qdrant__search_documents for policy RAG; collection name is `{COLLECTION}`
- sandbox__execute_python for projections and Monte Carlo style math

Do not invent table or collection names. Do not return other tenants' data.
If a tool is unavailable, say so rather than fabricating holdings.
"""

_model = ChatOpenAI(model=MODEL, temperature=0)
graph = create_agent(_model, tools=[], system_prompt=SYSTEM)
