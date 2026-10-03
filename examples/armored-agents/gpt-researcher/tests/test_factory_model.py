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
