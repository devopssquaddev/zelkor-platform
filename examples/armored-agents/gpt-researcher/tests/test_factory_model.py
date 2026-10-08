"""Factory maps gateway model ids without importing upstream."""
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from graph import _gateway_model  # noqa: E402


def test_gateway_model_openai_slash(monkeypatch):
    monkeypatch.delenv("STRATEGIC_LLM", raising=False)
    monkeypatch.setenv("DEFAULT_LLM_MODEL", "openai/gpt-4o-mini")
    assert _gateway_model() == "openai:gpt-4o-mini"


def test_gateway_model_already_colon(monkeypatch):
    monkeypatch.setenv("STRATEGIC_LLM", "openai:gpt-4o-mini")
    assert _gateway_model() == "openai:gpt-4o-mini"


def test_gateway_model_empty(monkeypatch):
    monkeypatch.delenv("STRATEGIC_LLM", raising=False)
    monkeypatch.delenv("DEFAULT_LLM_MODEL", raising=False)
    assert _gateway_model() == ""


def test_gateway_model_ollama_id_uses_openai_prefix(monkeypatch):
    monkeypatch.delenv("STRATEGIC_LLM", raising=False)
    monkeypatch.setenv("DEFAULT_LLM_MODEL", "gpt-oss:20b")
    assert _gateway_model() == "openai:gpt-oss:20b"


def test_pin_gateway_llms_overwrites_gptr_defaults(monkeypatch):
    from graph import _pin_gateway_llms

    monkeypatch.setenv("FAST_LLM", "openai:gpt-5.4-mini")
    monkeypatch.setenv("SMART_LLM", "openai:gpt-5.4")
    monkeypatch.setenv("STRATEGIC_LLM", "openai:gpt-5.4")
    _pin_gateway_llms("openai:gpt-oss:20b")
    assert os.environ["FAST_LLM"] == "openai:gpt-oss:20b"
    assert os.environ["SMART_LLM"] == "openai:gpt-oss:20b"
    assert os.environ["STRATEGIC_LLM"] == "openai:gpt-oss:20b"


def test_graph_factory_is_zero_arg():
    import inspect

    from graph import graph

    assert len(inspect.signature(graph).parameters) == 0


def test_factory_uses_mcp_inject_call_tool():
    text = (ROOT / "graph.py").read_text(encoding="utf-8")
    assert "from gpt_researcher" not in text
    assert "TAVILY_API_KEY" not in text
    assert "streamable_http" not in text
    assert "from mcp_inject import call_tool" in text
    assert "tavily__tavily_search" in text
    assert "tavily__tavily_research" in text
    assert "def write_todos" in text
    assert "FilesystemBackend" in text
    assert "awrite" not in text
    assert "object__write_text" in text
    assert "OBJECT_S3" not in text
    assert "AWS_" not in text
    assert "boto3" not in text
    assert "ZELKOR_RECURSION_LIMIT" in text
    assert "recursion_limit" in text
    assert "use_responses_api=False" in text
    assert "on_chain_start" in text
    assert "backend.cwd" in text


def test_tavily_search_payload_uses_query():
    from graph import _search_call

    assert _search_call("gVisor") == ("tavily__tavily_search", {"query": "gVisor"})


def test_save_run_dir_copies_files(tmp_path):
    from graph import save_run_dir

    text = "section draft"
    (tmp_path / "research").mkdir()
    (tmp_path / "research" / "intro.md").write_text(text, encoding="utf-8")
    (tmp_path / "todos.md").write_text("1. intro\n", encoding="utf-8")
    calls = []

    async def fake(name, args):
        calls.append((name, args))
        return '{"size": 13}'

    keys = asyncio.run(save_run_dir(fake, "a1b2c3d4", str(tmp_path)))
    assert keys == [
        "gpt-researcher/a1b2c3d4/research/intro.md",
        "gpt-researcher/a1b2c3d4/todos.md",
    ]
    assert calls[0] == (
        "object__write_text",
        {"key": keys[0], "text": text},
    )


def test_save_run_dir_mcp_error_does_not_raise(tmp_path):
    from graph import save_run_dir

    (tmp_path / "todos.md").write_text("1. intro\n", encoding="utf-8")

    async def fake(name, args):
        del name, args
        return "Error: MCP_URL is not set"

    keys = asyncio.run(save_run_dir(fake, "a1b2c3d4", str(tmp_path)))
    assert keys == []


def test_save_run_dir_stops_on_non_json(tmp_path):
    from graph import save_run_dir

    (tmp_path / "todos.md").write_text("1. intro\n", encoding="utf-8")

    async def fake(name, args):
        del name, args
        return "No writable volumes"

    keys = asyncio.run(save_run_dir(fake, "a1b2c3d4", str(tmp_path)))
    assert keys == []


def test_tavily_research_payload_uses_input():
    from graph import _research_call

    name, args = _research_call("sentry vs ptrace", "gVisor")
    assert name == "tavily__tavily_research"
    assert args == {"input": "sentry vs ptrace (overall topic: gVisor)"}
