"""Pydantic AI runtime behind zelkor-sidecar: serves the agent over A2A on 127.0.0.1:8080.

No local tools: every tool is an MCP tool on the sidecar loopback (``MCP_URL``), so code
runs in the gVisor sandbox (``sandbox__execute_python``) and calls are governed there.
The model talks to the sidecar's ``/v1`` (``OPENAI_BASE_URL``); the sidecar adds the key.
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import partial

import uvicorn
from fasta2a.broker import InMemoryBroker
from fasta2a.pydantic_ai import agent_to_a2a
from fasta2a.pydantic_ai._bridge import AgentWorker
from fasta2a.schema import Message, Part
from fasta2a.storage import InMemoryStorage
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from zelkor_runtime_spec import load_spec

logger = logging.getLogger("zelkor-runtime-pydantic-ai")

HOST = "127.0.0.1"
PORT = int(os.getenv("ZELKOR_RUNTIME_PORT", "8080"))


class UtcStorage(InMemoryStorage):
    """fasta2a 2.1.1 stamps naive local time; A2A requires RFC 3339 (UTC ``Z``)."""

    @staticmethod
    def _utc(task):
        status = task.get("status") or {}
        if status.get("timestamp") is not None:
            status["timestamp"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        return task

    async def submit_task(self, context_id, message):
        return self._utc(await super().submit_task(context_id, message))

    async def update_task(self, task_id, state, new_artifacts=None, new_messages=None):
        return self._utc(await super().update_task(task_id, state, new_artifacts, new_messages))

    def set_status_message(self, task_id: str, message: Message) -> None:
        self.tasks[task_id]["status"]["message"] = message


@dataclass
class LoggingWorker(AgentWorker):
    """fasta2a fails the task with no status message; log the cause and hand it to the caller.

    The cause is the exception type and message (no prompt bodies); it becomes the A2A status
    message of the failed task, which the sidecar returns as the run's error.
    """

    failures: dict[str, str] = field(default_factory=dict)

    async def run_task(self, params):
        try:
            await super().run_task(params)
        except Exception as exc:
            reason = f"{type(exc).__name__}: {str(exc)[:300]}"
            logger.error("task failed: %s", reason)
            self.failures[params["id"]] = reason
            raise

    async def _end_stream(self, task_id, context_id, state):
        reason = self.failures.pop(task_id, None)
        if state != "failed" or not reason:
            return await super()._end_stream(task_id, context_id, state)
        message = Message(role="agent", parts=[Part(text=reason)], message_id=f"{task_id}-failed",
                          task_id=task_id, context_id=context_id)
        if isinstance(self.storage, UtcStorage):
            self.storage.set_status_message(task_id, message)
        await self.publish_status(task_id, context_id, state, message=message)
        await self.broker.event_bus.close(task_id)


@asynccontextmanager
async def run_scoped_lifespan(app, worker):
    """Start the task manager and worker but do not enter the agent's toolsets.

    fasta2a's default lifespan opens MCP at startup; behind the sidecar there is no run
    (and so no tenant identity) yet, and the sidecar refuses it. Pydantic AI opens the
    MCP toolset inside each run instead.
    """
    async with app.task_manager:
        async with worker.run():
            yield


def build_app():
    spec = load_spec()
    model = OpenAIChatModel(spec.model, provider=OpenAIProvider(base_url=spec.llm_base_url, api_key="via-sidecar"))
    agent = Agent(model, name=spec.name, instructions=spec.instructions or None,
                  toolsets=[MCPToolset(spec.mcp_url)])
    storage, broker = UtcStorage(), InMemoryBroker()
    worker = LoggingWorker(agent=agent, broker=broker, storage=storage)
    return agent_to_a2a(agent, name=spec.name, url=f"http://{HOST}:{PORT}", storage=storage, broker=broker,
                        lifespan=partial(run_scoped_lifespan, worker=worker))


if __name__ == "__main__":
    from zelkor_logging import configure_logging

    configure_logging("zelkor-runtime-pydantic-ai")
    uvicorn.run(build_app(), host=HOST, port=PORT, log_level=os.getenv("ZELKOR_LOG_LEVEL", "info").lower())
