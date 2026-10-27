"""CE-14 shared runtime spec (agent.json + AGENTS.md) for Pydantic AI / CrewAI runtimes."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "images" / "runtime-common"))

from zelkor_runtime_spec import load_spec  # noqa: E402

LOOPBACK = {"OPENAI_BASE_URL": "http://127.0.0.1:8001/run/active/v1/",
            "MCP_URL": "http://127.0.0.1:8001/run/active/mcp"}


def _project(tmp_path, agent: dict, md: str | None = "Be brief."):
    (tmp_path / "agent.json").write_text(json.dumps(agent), encoding="utf-8")
    if md is not None:
        (tmp_path / "AGENTS.md").write_text(md, encoding="utf-8")
    return tmp_path


@pytest.fixture
def env(monkeypatch):
    for k, v in LOOPBACK.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("DEFAULT_LLM_MODEL", raising=False)
    return monkeypatch


def test_spec_reads_agent_and_strips_provider(tmp_path, env):
    spec = load_spec(_project(tmp_path, {"name": "desk", "model": "openai:gpt-4o-mini"}))
    assert (spec.name, spec.model, spec.instructions) == ("desk", "gpt-4o-mini", "Be brief.")
    assert spec.llm_base_url == "http://127.0.0.1:8001/run/active/v1"
    assert spec.mcp_url.endswith("/run/active/mcp")


def test_default_llm_model_wins(tmp_path, env):
    env.setenv("DEFAULT_LLM_MODEL", "gpt-oss:20b")
    spec = load_spec(_project(tmp_path, {"name": "desk", "model": "openai:gpt-4o"}))
    assert spec.model == "gpt-oss:20b"  # gateway ids may contain ':'; env value is used as-is


def test_no_model_or_no_loopback_fails(tmp_path, env):
    with pytest.raises(RuntimeError, match="no model"):
        load_spec(_project(tmp_path, {"name": "desk"}))
    env.delenv("MCP_URL")
    with pytest.raises(RuntimeError, match="sidecar loopback"):
        load_spec(_project(tmp_path, {"name": "desk", "model": "m"}))


def test_gateway_model_ids_with_colons_are_kept(tmp_path, env):
    assert load_spec(_project(tmp_path, {"name": "d", "model": "gpt-oss:20b"})).model == "gpt-oss:20b"
    assert load_spec(_project(tmp_path, {"name": "d", "model": "ollama:qwen3:8b"})).model == "qwen3:8b"
