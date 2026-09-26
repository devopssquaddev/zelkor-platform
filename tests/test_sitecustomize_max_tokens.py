"""Unit tests for ZELKOR_MAX_TOKENS clamp in images/aegra/sitecustomize.py."""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
SITECUSTOMIZE = ROOT / "images" / "aegra" / "sitecustomize.py"


def _load_chat_openai_patch(monkeypatch, cap: str):
    monkeypatch.setenv("ZELKOR_MAX_TOKENS", cap)
    # Minimal stubs so sitecustomize import does not need full aegra image tree.
    for mod in ("auth_inject", "wrap_identity", "trace_wrap", "mcp_inject"):
        sys.modules.setdefault(mod, MagicMock())
    sys.modules["zelkor_logging"] = MagicMock(configure_logging=MagicMock())
    spec = importlib.util.spec_from_file_location("sitecustomize_test", SITECUSTOMIZE)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    # ChatOpenAI patch runs at import time; provide a fake langchain_openai.
    captured: list[dict] = []

    class FakeChatOpenAI:
        _zelkor_nonstream_patched = False

        def __init__(self, *args, **kwargs):
            captured.append(dict(kwargs))

    fake_lc = MagicMock(ChatOpenAI=FakeChatOpenAI)
    monkeypatch.setitem(sys.modules, "langchain_openai", fake_lc)
    spec.loader.exec_module(mod)
    return FakeChatOpenAI, captured


def test_max_tokens_default_when_cap_set(monkeypatch):
    cls, captured = _load_chat_openai_patch(monkeypatch, "4096")
    cls()
    assert captured[-1]["max_tokens"] == 4096


def test_max_tokens_clamp_when_caller_higher(monkeypatch):
    cls, captured = _load_chat_openai_patch(monkeypatch, "1000")
    cls(max_tokens=8000)
    assert captured[-1]["max_tokens"] == 1000


def test_max_completion_tokens_clamp(monkeypatch):
    cls, captured = _load_chat_openai_patch(monkeypatch, "500")
    cls(max_completion_tokens=2000)
    assert captured[-1]["max_completion_tokens"] == 500
