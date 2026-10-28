"""CrewAI runtime keeps tool panels (prompt / tool content) out of stdout below DEBUG (no cluster)."""
from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "images" / "runtime-crewai"))


@pytest.fixture
def crewai(monkeypatch):
    """Stand-in for crewai 1.15: verbose singleton formatter + ContextVar suppression flag."""
    state = {"suppress": False}
    formatter = types.SimpleNamespace(verbose=True)
    listener_mod = types.ModuleType("crewai.events.event_listener")
    listener_mod.event_listener = types.SimpleNamespace(formatter=formatter)
    printer_mod = types.ModuleType("crewai_core.printer")
    printer_mod.set_suppress_console_output = lambda v: state.__setitem__("suppress", v)
    for name, mod in {"crewai": types.ModuleType("crewai"), "crewai.events": types.ModuleType("crewai.events"),
                      "crewai.events.event_listener": listener_mod, "crewai_core": types.ModuleType("crewai_core"),
                      "crewai_core.printer": printer_mod}.items():
        monkeypatch.setitem(sys.modules, name, mod)
    return formatter, state


def test_info_turns_off_panels_and_suppresses_console(crewai, monkeypatch):
    formatter, state = crewai
    monkeypatch.setenv("ZELKOR_LOG_LEVEL", "INFO")
    quiet = importlib.reload(importlib.import_module("quiet_console"))
    assert quiet.install() is True
    assert formatter.verbose is False and state["suppress"] is True


def test_debug_keeps_crewai_console(crewai, monkeypatch):
    formatter, state = crewai
    monkeypatch.setenv("ZELKOR_LOG_LEVEL", "DEBUG")
    quiet = importlib.reload(importlib.import_module("quiet_console"))
    assert quiet.install() is False
    assert formatter.verbose is True and state["suppress"] is False


def test_entrypoint_installs_and_suppresses_per_turn():
    src = (ROOT / "images" / "runtime-crewai" / "zelkor_runtime.py").read_text()
    assert "quiet_console.install()" in src and "quiet_console.suppress()" in src
