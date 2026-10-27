"""CrewAI runtime behind zelkor-sidecar: one agent served over A2A on 127.0.0.1:8080.

CrewAI's open-source A2A support provides the Agent Card (``A2AServerConfig``) and the
task executor (``crewai.a2a.utils.task.execute``); this entrypoint only wires them into
the a2a-sdk server it depends on. No local tools: tools come from the sidecar MCP loopback
(``MCP_URL``), the LLM from the sidecar ``/v1`` (``OPENAI_BASE_URL``).
"""
from __future__ import annotations

import logging
import os

import uvicorn
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.apps import A2AStarletteApplication
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from crewai import LLM, Agent
from crewai.a2a.config import A2AServerConfig
from crewai.a2a.utils.task import cancel as crew_cancel
from crewai.a2a.utils.task import execute as crew_execute
from crewai.mcp import MCPServerHTTP

from zelkor_runtime_spec import load_spec

logger = logging.getLogger("zelkor-runtime-crewai")

HOST = "127.0.0.1"
PORT = int(os.getenv("ZELKOR_RUNTIME_PORT", "8080"))


class CrewExecutor(AgentExecutor):
    def __init__(self, agent: Agent) -> None:
        self.agent = agent

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        try:
            await crew_execute(self.agent, context, event_queue)
        except Exception as exc:
            logger.error("task failed: %s: %s", type(exc).__name__, str(exc)[:300])
            raise

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        await crew_cancel(context, event_queue)


def build_app():
    spec = load_spec()
    url = f"http://{HOST}:{PORT}"
    llm = LLM(model=f"openai/{spec.model}", base_url=spec.llm_base_url, api_key="via-sidecar")
    agent = Agent(
        role=spec.name,
        goal=spec.instructions or f"Help the user as {spec.name}.",
        backstory=spec.instructions or "",
        llm=llm,
        mcps=[MCPServerHTTP(url=spec.mcp_url, streamable=True)],
        tools=[],
        allow_delegation=False,
        a2a=A2AServerConfig(name=spec.name, url=url),
    )
    card = agent.to_agent_card(url)
    handler = DefaultRequestHandler(agent_executor=CrewExecutor(agent), task_store=InMemoryTaskStore())
    return A2AStarletteApplication(agent_card=card, http_handler=handler).build()


if __name__ == "__main__":
    from zelkor_logging import configure_logging

    configure_logging("zelkor-runtime-crewai")
    uvicorn.run(build_app(), host=HOST, port=PORT, log_level=os.getenv("ZELKOR_LOG_LEVEL", "info").lower())
