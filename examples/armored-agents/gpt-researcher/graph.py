"""Aegra factory for unmodified GPT Researcher deep_agents.build_agent."""
from __future__ import annotations

import logging
import os
import tempfile
import uuid
from typing import Any

logger = logging.getLogger("zelkor-armored-gpt-researcher")


def _gateway_model() -> str:
    raw = (os.getenv("STRATEGIC_LLM") or os.getenv("DEFAULT_LLM_MODEL") or "").strip()
    if not raw:
        return ""
    prefix, sep, rest = raw.partition("/")
    if sep and ":" not in prefix:
        return f"{prefix}:{rest}"
    return raw


def graph(config: Any = None, runtime: Any = None) -> Any:
    from deep_agents.agent import build_agent

    run_dir = os.path.join(tempfile.gettempdir(), f"gptr-{uuid.uuid4().hex[:8]}")
    os.makedirs(run_dir, exist_ok=True)
    task: dict[str, Any] = {
        "query": "",
        "source": "web",
        "max_sections": 3,
        "verbose": False,
        "follow_guidelines": False,
    }
    model = _gateway_model()
    if model:
        task["model"] = model
        os.environ.setdefault("STRATEGIC_LLM", model)
    logger.info(
        "graph_build",
        extra={"event": "graph_build", "component": "zelkor-armored-gpt-researcher"},
    )
    return build_agent(task, run_dir)
