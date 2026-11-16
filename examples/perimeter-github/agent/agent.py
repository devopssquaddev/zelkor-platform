"""Repo-triage agent: the stock Zelkor Pydantic AI runtime plus two plain Python GitHub tools.

Served over A2A on 127.0.0.1:8080 behind zelkor-sidecar. Model calls go to OPENAI_BASE_URL (the
sidecar); GitHub calls go to ZELKOR_API_GITHUB_URL (the sidecar, then the gateway relay).
"""
from __future__ import annotations

import os
from functools import partial

import uvicorn
from fasta2a.broker import InMemoryBroker
from fasta2a.pydantic_ai import agent_to_a2a
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from github_tools import github_read, github_write
from zelkor_runtime import HOST, PORT, LoggingWorker, UtcStorage, run_scoped_lifespan
from zelkor_runtime_spec import load_spec


def build_app():
    spec = load_spec()
    model = OpenAIChatModel(spec.model, provider=OpenAIProvider(base_url=spec.llm_base_url, api_key="via-sidecar"))
    agent = Agent(model, name=spec.name, instructions=spec.instructions or None,
                  tools=[github_read, github_write])
    storage, broker = UtcStorage(), InMemoryBroker()
    worker = LoggingWorker(agent=agent, broker=broker, storage=storage)
    return agent_to_a2a(agent, name=spec.name, url=f"http://{HOST}:{PORT}", storage=storage, broker=broker,
                        lifespan=partial(run_scoped_lifespan, worker=worker))


if __name__ == "__main__":
    from zelkor_logging import configure_logging

    configure_logging("zelkor-example-perimeter-github")
    uvicorn.run(build_app(), host=HOST, port=PORT, log_level=os.getenv("ZELKOR_LOG_LEVEL", "info").lower())
