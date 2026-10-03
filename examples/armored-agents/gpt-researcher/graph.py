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
    if raw.startswith("openai:"):
        return raw
    prefix, sep, rest = raw.partition("/")
    if sep and ":" not in prefix:
        return f"{prefix}:{rest}"
    if "/" not in raw:
        return f"openai:{raw}"
    return raw


def _pin_gateway_llms(model: str) -> None:
    """GPTR defaults FAST/SMART/STRATEGIC to openai:gpt-5.4* — overwrite for the in-cluster gateway."""
    for key in ("FAST_LLM", "SMART_LLM", "STRATEGIC_LLM"):
        os.environ[key] = model


_m = _gateway_model()
if _m:
    _pin_gateway_llms(_m)


def graph() -> Any:
    """0-arg Aegra factory. Two untyped params fail classify_factory on Aegra v0.10.4."""
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
        _pin_gateway_llms(model)
    logger.info(
        "graph_build",
        extra={"event": "graph_build", "component": "zelkor-armored-gpt-researcher"},
    )
    return build_agent(task, run_dir)
