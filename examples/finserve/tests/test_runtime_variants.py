"""Offline: FinServe advisor/quant as deploy-first projects for the sidecar runtimes (a2a / opencode).

Each folder under ``examples/finserve/runtimes/`` must stay deploy-first (no graphs map), load with the
shared runtime spec, and name the same MCP tools as its Aegra graph module (``MCP_INJECT_TOOLS``).
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
FINSERVE = ROOT / "examples" / "finserve"
sys.path.insert(0, str(ROOT / "images" / "runtime-common"))
sys.path.insert(0, str(ROOT / "cli" / "src"))

from zelkor.detect import detect  # noqa: E402
from zelkor_runtime_spec import load_spec  # noqa: E402

# runtime folder -> (Aegra graph module, `zelkor deploy --tools` scope)
AGENTS = {
    "advisor": ("advisor_agent.py", "postgres"),
    "quant": ("quant_agent.py", "sandbox"),
}
TOOL = re.compile(r"\b[a-z]+__[a-z_]+\b")


def _inject_tools(module: str) -> set[str]:
    tree = ast.parse((FINSERVE / "chart" / "files" / module).read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "MCP_INJECT_TOOLS" for t in node.targets):
            return set(ast.literal_eval(node.value))
    raise AssertionError(f"{module} has no MCP_INJECT_TOOLS")


@pytest.mark.parametrize("name", sorted(AGENTS))
def test_runtime_variant_is_deploy_first(name):
    folder = FINSERVE / "runtimes" / name
    assert not (folder / "langgraph.json").exists() and not (folder / "aegra.json").exists()
    shape = detect(folder)
    assert shape.kind == "deploy-first"
    assert shape.graph_id == f"finserve-{name}"


@pytest.mark.parametrize("name", sorted(AGENTS))
def test_runtime_variant_loads_spec(name, monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "http://127.0.0.1:8001/v1")
    monkeypatch.setenv("MCP_URL", "http://127.0.0.1:8001/mcp")
    monkeypatch.setenv("DEFAULT_LLM_MODEL", "gpt-4o-mini")
    spec = load_spec(FINSERVE / "runtimes" / name)
    assert spec.name == f"finserve-{name}"
    assert spec.instructions.strip()


@pytest.mark.parametrize("name", sorted(AGENTS))
def test_runtime_variant_names_same_tools_as_aegra_graph(name):
    module, scope = AGENTS[name]
    named = set(TOOL.findall((FINSERVE / "runtimes" / name / "AGENTS.md").read_text(encoding="utf-8")))
    assert named == _inject_tools(module)
    assert all(t.startswith(f"{scope}__") for t in named), f"{named} outside --tools {scope}"
