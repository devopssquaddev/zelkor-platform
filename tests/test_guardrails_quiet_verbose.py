"""NeMo server must not print prompts/completions or mute Zelkor JSON logs (no cluster)."""
from __future__ import annotations

import importlib
import logging
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "images" / "guardrails"))


@pytest.fixture
def nemo(monkeypatch):
    """Stand-in for nemoguardrails 0.24.1: llmrails imports set_verbose by name."""
    calls = []

    def set_verbose(verbose, llm_calls=False, **_kw):  # vendor: adds a console handler, mutes others
        calls.append((verbose, llm_calls))
        for handler in logging.getLogger().handlers:
            handler.setLevel(logging.WARNING)

    verbose_mod = types.ModuleType("nemoguardrails.logging.verbose")
    verbose_mod.set_verbose = set_verbose
    llmrails_mod = types.ModuleType("nemoguardrails.rails.llm.llmrails")
    llmrails_mod.set_verbose = set_verbose
    for name, mod in {
        "nemoguardrails": types.ModuleType("nemoguardrails"),
        "nemoguardrails.logging": types.ModuleType("nemoguardrails.logging"),
        "nemoguardrails.logging.verbose": verbose_mod,
        "nemoguardrails.rails": types.ModuleType("nemoguardrails.rails"),
        "nemoguardrails.rails.llm": types.ModuleType("nemoguardrails.rails.llm"),
        "nemoguardrails.rails.llm.llmrails": llmrails_mod,
    }.items():
        monkeypatch.setitem(sys.modules, name, mod)
    return calls, verbose_mod, llmrails_mod


def _handler():
    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO)
    logging.getLogger().addHandler(handler)
    return handler


def test_server_verbose_is_a_noop_at_info(nemo, monkeypatch):
    calls, verbose_mod, llmrails_mod = nemo
    monkeypatch.setenv("ZELKOR_LOG_LEVEL", "INFO")
    quiet = importlib.reload(importlib.import_module("quiet_verbose"))
    assert quiet.install() is True
    handler = _handler()
    try:
        llmrails_mod.set_verbose(True, llm_calls=True)  # what LLMRails(verbose=True) calls
        verbose_mod.set_verbose(True)
    finally:
        logging.getLogger().removeHandler(handler)
    assert calls == []  # no console handler, no prompt bodies
    assert handler.level == logging.INFO  # Zelkor JSON handler not muted


def test_debug_keeps_vendor_verbose(nemo, monkeypatch):
    calls, _verbose_mod, llmrails_mod = nemo
    monkeypatch.setenv("ZELKOR_LOG_LEVEL", "DEBUG")
    quiet = importlib.reload(importlib.import_module("quiet_verbose"))
    assert quiet.install() is False
    llmrails_mod.set_verbose(True, llm_calls=True)
    assert calls == [(True, True)]


def test_boot_installs_patch_before_the_nemo_cli():
    # The server runs under opentelemetry-instrument, whose sitecustomize shadows ours.
    src = (ROOT / "images" / "guardrails" / "boot.py").read_text()
    assert src.index("install_quiet_verbose()") < src.index("from nemoguardrails.cli import app")
