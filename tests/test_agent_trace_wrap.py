"""Unit tests for Aegra Langfuse run-root wrap (no cluster)."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "images" / "aegra"))

from trace_wrap import (  # noqa: E402
    assistant_output_text,
    clip_io,
    record_span_io,
    run_span_name,
    user_prompt_text,
)


class _FakeSpan:
    def __init__(self) -> None:
        self.attrs: dict = {}
        self.events: list = []

    def set_attribute(self, key, value) -> None:
        self.attrs[key] = value

    def add_event(self, name, attributes=None) -> None:
        self.events.append((name, attributes or {}))


def test_user_prompt_from_agent_protocol_messages():
    text = user_prompt_text(
        {"messages": [{"role": "human", "content": "What is my balance?"}]}
    )
    assert text == "What is my balance?"


def test_user_prompt_from_langchain_human_message():
    msg = MagicMock()
    msg.type = "human"
    msg.role = None
    msg.content = "hello"
    assert user_prompt_text({"messages": [msg]}) == "hello"


def test_assistant_output_last_ai_message():
    text = assistant_output_text(
        {
            "messages": [
                {"role": "human", "content": "hi"},
                {"role": "assistant", "content": "first"},
                {"role": "assistant", "content": "final"},
            ]
        }
    )
    assert text == "final"


def test_assistant_output_from_astream_values_tuple():
    chunk = ("values", {"messages": [{"role": "assistant", "content": "ok"}]})
    assert assistant_output_text(chunk) == "ok"


def test_clip_io_truncates():
    assert clip_io("abcd", limit=3) == "abc…"
    assert clip_io("ab", limit=3) == "ab"


def test_record_span_io_sets_langfuse_and_gen_ai():
    span = _FakeSpan()
    record_span_io(span, prompt="in", completion="out")
    assert span.attrs["langfuse.observation.input"] == "in"
    assert span.attrs["langfuse.observation.output"] == "out"
    assert span.attrs["input.value"] == "in"
    assert span.attrs["output.value"] == "out"
    names = [n for n, _ in span.events]
    assert "gen_ai.content.prompt" in names
    assert "gen_ai.content.completion" in names


def test_run_span_name_prefers_bound_graph_id(monkeypatch):
    graph = MagicMock()
    graph.name = "compiled"
    monkeypatch.setenv("ZELKOR_GRAPH_ID", "env-graph")
    monkeypatch.setattr("trace_wrap.bound_graph_id", lambda: "advisor")
    assert run_span_name(graph) == "advisor"


def test_run_span_name_falls_back_to_env(monkeypatch):
    monkeypatch.setenv("ZELKOR_GRAPH_ID", "worker-graph")
    monkeypatch.setattr("trace_wrap.bound_graph_id", lambda: None)
    graph = MagicMock()
    graph.name = "LangGraph"
    assert run_span_name(graph) == "worker-graph"


def test_sitecustomize_and_dockerfile_ship_trace_wrap():
    root = Path(__file__).resolve().parents[1]
    site = (root / "images/aegra/sitecustomize.py").read_text()
    wrap = (root / "images/aegra/trace_wrap.py").read_text()
    dockerfile = (root / "images/aegra/Dockerfile").read_text()
    assert "from trace_wrap import" in site
    assert "patch_otel_setup" in site
    assert "HTTPXClientInstrumentor(" not in site
    assert "HTTPXClientInstrumentor(" not in wrap
    assert "ChatOpenAI.request" in wrap
    assert "Pregel" in wrap
    assert "astream_events" in wrap
    assert "langfuse.observation.input" in wrap
    assert "trace_wrap.py" in dockerfile
