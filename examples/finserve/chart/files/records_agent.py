"""FinServe records — statement text windows (Mode B drop-in).

The bank pipeline writes the full statement to object storage. This graph
reads a key and a short UTF-8 window. It does not hold S3 credentials.
"""
from __future__ import annotations

import os

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

MCP_INJECT_TOOLS = ("object__list", "object__read_text")

MODEL = os.getenv("DEFAULT_LLM_MODEL", "")

SYSTEM = """FinServe Records. Use object__list and object__read_text only.
Read statements by key and a short text window. Do not ask for the whole file.
If eof is false, call object__read_text again with a higher offset."""

_model = ChatOpenAI(model=MODEL, temperature=0)
graph = create_agent(
    _model,
    tools=[],
    system_prompt=SYSTEM,
)
