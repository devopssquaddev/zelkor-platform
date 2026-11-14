"""A failed pydantic-ai runtime task tells the caller why (A2A status message), not just "failed".

fasta2a marks a task failed with no status message; the sidecar then reports
`A2A task TASK_STATE_FAILED: ` and the cause (a denied tool, a model error) is lost.

Needs the runtime's own dependencies (skips otherwise):
  pip install -r images/runtime-pydantic-ai/requirements.txt pytest
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for p in ("runtime-pydantic-ai", "runtime-common"):
    sys.path.insert(0, str(ROOT / "images" / p))

pytest.importorskip("fasta2a")
pytest.importorskip("pydantic_ai")

from fasta2a.broker import InMemoryBroker  # noqa: E402
from opentelemetry.trace import INVALID_SPAN  # noqa: E402
from pydantic_ai import Agent  # noqa: E402
from pydantic_ai.models.function import FunctionModel  # noqa: E402

try:
    import zelkor_runtime  # noqa: E402
except ImportError as exc:  # the repo venv lacks the runtime's MCP client deps
    pytest.skip(f"runtime deps missing ({exc}): pip install -r images/runtime-pydantic-ai/requirements.txt",
                allow_module_level=True)


def _failing_agent() -> Agent:
    def model(messages, info):
        raise RuntimeError("Tool 'aigateway__call' exceeded max retries count of 1")
    return Agent(FunctionModel(model))


def _status_text(status: dict) -> str:
    return " ".join(p.get("text", "") for p in ((status.get("message") or {}).get("parts") or []))


def test_failed_task_carries_the_cause():
    async def go():
        storage, broker = zelkor_runtime.UtcStorage(), InMemoryBroker()
        worker = zelkor_runtime.LoggingWorker(agent=_failing_agent(), broker=broker, storage=storage)
        message = {"role": "user", "kind": "message", "message_id": "m1",
                   "parts": [{"kind": "text", "text": "hi"}]}
        async with broker:
            task = await storage.submit_task("ctx-1", message)
            seen: list[dict] = []

            async def listen():
                async with broker.event_bus.subscribe(task["id"]) as stream:
                    async for event in stream:
                        seen.append(event)

            listener = asyncio.create_task(listen())
            await asyncio.sleep(0)
            await worker._handle_task_operation({
                "operation": "run", "_current_span": INVALID_SPAN,
                "params": {"id": task["id"], "context_id": "ctx-1", "message": message},
            })
            await asyncio.wait_for(listener, 5)
        stored = await storage.load_task(task["id"])
        return stored, seen

    stored, seen = asyncio.run(go())
    assert stored["status"]["state"] == "failed"
    assert "exceeded max retries" in _status_text(stored["status"]), stored["status"]
    final = [e for e in seen if "status_update" in str(e)]
    assert final and "exceeded max retries" in str(final[-1]), seen
