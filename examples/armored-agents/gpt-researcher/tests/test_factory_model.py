"""Factory maps gateway model ids without importing upstream."""
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
