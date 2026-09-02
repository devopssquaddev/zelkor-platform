import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "images" / "langfuse-seed"))

from seed import extra_backend_names, keep_mcp_tool, parse_extra_projects, managed_projects, fast_hashed_secret_key, display_secret_key, resolve_custom_models, to_llm_tool, to_openai_function  # noqa: E402
import seed as seed_mod


def test_keep_native_prefixes_only_unless_extra():
    extras = extra_backend_names('[{"name":"acme-tools","url":"http://x"}]')
    assert keep_mcp_tool("postgres__query", extras)
    assert keep_mcp_tool("qdrant__upsert_document", extras)
    assert keep_mcp_tool("egress__call_external_api", extras)
    assert keep_mcp_tool("acme-tools__ping", extras)
    assert not keep_mcp_tool("servicenow__get", extras)
    assert not keep_mcp_tool("acme-tools__ping", [])


def test_resolve_custom_models_does_not_wipe_existing():
    assert resolve_custom_models(["gpt-oss:20b"], ["kept"]) == ["gpt-oss:20b"]
    assert resolve_custom_models([], ["ui-added"]) == ["ui-added"]
    assert resolve_custom_models([], []) == []


def test_to_openai_function_schema():
    fn = to_openai_function(
        {
            "name": "postgres__query",
            "description": "SQL",
            "inputSchema": {"type": "object", "properties": {"sql": {"type": "string"}}},
        }
    )
    assert fn["type"] == "function"
    assert fn["function"]["name"] == "postgres__query"
    assert "sql" in fn["function"]["parameters"]["properties"]


def test_to_llm_tool_is_flat_playground_row():
    tool = to_llm_tool(
        {
            "name": "qdrant__search_documents",
            "description": "Search",
            "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}},
        }
    )
    assert tool["name"] == "qdrant__search_documents"
    assert "function" not in tool
    assert tool["parameters"]["type"] == "object"
    assert "query" in tool["parameters"]["properties"]


def test_parse_extra_projects_skips_incomplete():
    raw = json.dumps(
        [
            {
                "id": "finserve",
                "name": "FinServe AI",
                "publicKey": "pk-lf-finserve-dev-00000000000000000000",
                "secretKey": "sk-lf-finserve-dev-00000000000000000000",
            },
            {"id": "no-keys"},
        ]
    )
    projects = parse_extra_projects(raw)
    assert len(projects) == 1
    assert projects[0]["id"] == "finserve"
    assert parse_extra_projects("") == []
    assert parse_extra_projects("not-json") == []


def test_managed_projects_init_then_extras(monkeypatch):
    extra = json.dumps(
        [
            {
                "id": "finserve",
                "name": "FinServe AI",
                "publicKey": "pk-extra",
                "secretKey": "sk-extra",
            }
        ]
    )
    monkeypatch.setattr(seed_mod, "PROJECT_ID", "zelkor-platform")
    monkeypatch.setattr(seed_mod, "PUBLIC_KEY", "pk-init")
    monkeypatch.setattr(seed_mod, "SECRET_KEY", "sk-init")
    monkeypatch.setattr(seed_mod, "EXTRA_PROJECTS_RAW", extra)
    ids = [p["id"] for p in managed_projects()]
    assert ids == ["zelkor-platform", "finserve"]


def test_managed_projects_skips_duplicate_init_key(monkeypatch):
    extra = json.dumps(
        [{"id": "stolen", "name": "x", "publicKey": "pk-init", "secretKey": "sk-init"}]
    )
    monkeypatch.setattr(seed_mod, "PROJECT_ID", "zelkor-platform")
    monkeypatch.setattr(seed_mod, "PUBLIC_KEY", "pk-init")
    monkeypatch.setattr(seed_mod, "SECRET_KEY", "sk-init")
    monkeypatch.setattr(seed_mod, "EXTRA_PROJECTS_RAW", extra)
    ids = [p["id"] for p in managed_projects()]
    assert ids == ["zelkor-platform"]


def test_finserve_overlay_does_not_steal_init():
    overlay = Path(__file__).resolve().parents[1] / "examples/finserve/chart/values-platform-overlay.yaml"
    raw = overlay.read_text()
    assert "extraProjects:" in raw
    assert "projectId:" not in raw


def test_helm_extra_projects_on_seed_job_and_nemo():
    import subprocess

    root = Path(__file__).resolve().parents[1]
    chart = root / "charts/zelkor-platform"
    local = root / "profiles/values-local.yaml"
    overlay = root / "examples/finserve/chart/values-platform-overlay.yaml"
    try:
        seed = subprocess.run(
            [
                "helm",
                "template",
                "zelkor",
                str(chart),
                "-f",
                str(local),
                "-f",
                str(overlay),
                "-s",
                "templates/langfuse/job-surfaces-seed.yaml",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        nemo = subprocess.run(
            [
                "helm",
                "template",
                "zelkor",
                str(chart),
                "-f",
                str(local),
                "-f",
                str(overlay),
                "-s",
                "templates/guardrails/deployment.yaml",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        import pytest

        pytest.skip("helm not installed")
    if seed.returncode != 0:
        raise AssertionError(seed.stderr or seed.stdout)
    if nemo.returncode != 0:
        raise AssertionError(nemo.stderr or nemo.stdout)
    assert "LANGFUSE_EXTRA_PROJECTS" in seed.stdout
    assert "pk-lf-finserve-dev-00000000000000000000" in seed.stdout
    assert "LANGFUSE_EXTRA_OTLP" in nemo.stdout
    assert "pk-lf-finserve-dev-00000000000000000000" in nemo.stdout


def test_fast_hashed_secret_key_is_stable():
    first = fast_hashed_secret_key("sk-lf-x", "salt")
    second = fast_hashed_secret_key("sk-lf-x", "salt")
    assert first == second
    assert first != fast_hashed_secret_key("sk-lf-x", "other")
    assert display_secret_key("sk-lf-abcdef1234") == "sk-lf-...1234"
