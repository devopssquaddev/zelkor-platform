"""Unit tests for Aegra Langfuse run-root wrap (no cluster)."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "images" / "aegra"))

from trace_wrap import (  # noqa: E402
    assistant_output_text,
    clip_io,
    identity_headers,
    openinference_span_for_run,
    record_span_io,
    run_identity,
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


def test_assistant_output_from_langgraph_checkpoint():
    ckpt = {
        "step": 3,
        "type": "checkpoint",
        "payload": {
            "config": {"thread_id": "t"},
            "channel_values": {
                "messages": [
                    {"role": "human", "content": "hi"},
                    {"role": "assistant", "content": "policy text"},
                ]
            },
        },
    }
    assert assistant_output_text(ckpt) == "policy text"


def test_assistant_output_skips_empty_checkpoint():
    assert assistant_output_text({"step": 3, "type": "checkpoint", "payload": {"config": {}}}) == ""


def test_run_identity_and_headers():
    ident = run_identity(
        {"graph_id": "finserve-advisor", "thread_id": "th-1", "user_id": "Bank_Alpha"},
        public_key="pk-x",
    )
    assert ident["langfuse.trace.name"] == "finserve-advisor"
    assert ident["langfuse.session.id"] == "th-1"
    assert ident["langfuse.user.id"] == "Bank_Alpha"
    assert ident["zelkor.langfuse.pk"] == "pk-x"
    headers = identity_headers(ident)
    assert headers["x-zelkor-langfuse-trace-name"] == "finserve-advisor"
    assert headers["x-zelkor-langfuse-session-id"] == "th-1"
    assert headers["x-zelkor-langfuse-user-id"] == "Bank_Alpha"
    assert headers["x-zelkor-langfuse-pk"] == "pk-x"


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


def test_openinference_span_for_run_uses_get_span():
    span = object()
    handler = MagicMock()
    handler.get_span.return_value = span
    rm = MagicMock()
    rm.run_id = "run-1"
    rm.handlers = [handler]
    rm.inheritable_handlers = []
    assert openinference_span_for_run(rm) is span
    handler.get_span.assert_called_once_with("run-1")


def test_openinference_span_for_run_uses_instrumentor_when_handlers_empty():
    span = object()
    inst = MagicMock()
    inst.get_span.return_value = span
    # Do not monkeypatch.setattr(dotted) — that import_module's openinference
    # and fails when the test venv has no OpenInference (Gate A requirements-dev).
    from types import ModuleType

    root = ModuleType("openinference")
    root.__path__ = []  # type: ignore[attr-defined]
    instr = ModuleType("openinference.instrumentation")
    instr.__path__ = []  # type: ignore[attr-defined]
    mod = ModuleType("openinference.instrumentation.langchain")
    mod.LangChainInstrumentor = lambda: inst  # type: ignore[attr-defined]
    sys.modules["openinference"] = root
    sys.modules["openinference.instrumentation"] = instr
    sys.modules["openinference.instrumentation.langchain"] = mod
    rm = MagicMock()
    rm.run_id = "run-3"
    rm.handlers = []
    rm.inheritable_handlers = []
    assert openinference_span_for_run(rm) is span


def test_openinference_span_for_run_falls_back_to_spans_by_run():
    span = object()
    handler = MagicMock(spec=[])
    handler._spans_by_run = {"run-2": span}
    rm = MagicMock()
    rm.run_id = "run-2"
    rm.handlers = []
    rm.inheritable_handlers = [handler]
    assert openinference_span_for_run(rm) is span


def test_sitecustomize_and_dockerfile_ship_trace_wrap():
    root = Path(__file__).resolve().parents[1]
    site = (root / "images/aegra/sitecustomize.py").read_text()
    wrap = (root / "images/aegra/trace_wrap.py").read_text()
    dockerfile = (root / "images/aegra/Dockerfile").read_text()
    assert "from trace_wrap import" in site
    assert "attach_langfuse_project_baggage" in site
    assert "patch_otel_setup" in site
    assert "HTTPXClientInstrumentor(" not in site
    assert "HTTPXClientInstrumentor(" not in wrap
    assert "ChatOpenAI.request" in wrap
    assert "Pregel" in wrap
    assert "astream_events" in wrap
    assert "langfuse.observation.input" in wrap
    assert "trace_wrap.py" in dockerfile
    assert "chmod 644" in dockerfile
    assert "sitecustomize.py" in dockerfile
