import json
import sys
from pathlib import Path

import pytest

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
                "id": "team-a",
                "name": "Team A",
                "publicKey": "pk-lf-team-a-dev-00000000000000000000",
                "secretKey": "sk-lf-team-a-dev-00000000000000000000",
            },
            {"id": "no-keys"},
        ]
    )
    projects = parse_extra_projects(raw)
    assert len(projects) == 1
    assert projects[0]["id"] == "team-a"
    assert parse_extra_projects("") == []
    assert parse_extra_projects("not-json") == []


def test_managed_projects_init_then_extras(monkeypatch):
    extra = json.dumps(
        [
            {
                "id": "team-a",
                "name": "Team A",
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
    assert ids == ["zelkor-platform", "team-a"]


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
    assert "projectId:" not in raw
    assert "langfuse.init" not in raw


def test_helm_extra_projects_on_seed_job_and_nemo():
    import subprocess
    import tempfile

    root = Path(__file__).resolve().parents[1]
    chart = root / "charts/zelkor-platform"
    local = root / "profiles/values-local.yaml"
    extra_overlay = """
langfuse:
  extraProjects:
    - id: team-a
      name: Team A
      publicKey: pk-lf-team-a-dev-00000000000000000000
      secretKey: sk-lf-team-a-dev-00000000000000000000
"""
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as fh:
            fh.write(extra_overlay)
            extra_path = fh.name
        seed = subprocess.run(
            [
                "helm",
                "template",
                "zelkor",
                str(chart),
                "-f",
                str(local),
                "-f",
                extra_path,
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
                extra_path,
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
    finally:
        try:
            Path(extra_path).unlink(missing_ok=True)
        except NameError:
            pass
    if seed.returncode != 0:
        raise AssertionError(seed.stderr or seed.stdout)
    if nemo.returncode != 0:
        raise AssertionError(nemo.stderr or nemo.stdout)
    assert "LANGFUSE_EXTRA_PROJECTS" in seed.stdout
    assert "pk-lf-team-a-dev-00000000000000000000" in seed.stdout
    assert "LANGFUSE_EXTRA_OTLP" in nemo.stdout
    assert "pk-lf-team-a-dev-00000000000000000000" in nemo.stdout


def test_seed_admin_created(monkeypatch):
    monkeypatch.setattr(seed_mod, "LANGFUSE_HOST", "http://lf")
    monkeypatch.setattr(seed_mod, "_admin_exists_sql", lambda email: False)
    monkeypatch.setattr(seed_mod, "_signup", lambda e, p, n: (200, "{}"))
    assert seed_mod.seed_admin_user("a@b.c", "secret", "Admin") == "created"


def test_seed_admin_exists_http(monkeypatch):
    monkeypatch.setattr(seed_mod, "LANGFUSE_HOST", "http://lf")
    monkeypatch.setattr(seed_mod, "_admin_exists_sql", lambda email: False)
    monkeypatch.setattr(seed_mod, "_signup", lambda e, p, n: (422, '{"message":"User already exists"}'))
    assert seed_mod.seed_admin_user("a@b.c", "secret") == "exists"


def test_seed_admin_exists_sql(monkeypatch):
    monkeypatch.setattr(seed_mod, "_admin_exists_sql", lambda email: True)

    def boom(*_a, **_k):
        raise AssertionError("signup should not run")

    monkeypatch.setattr(seed_mod, "_signup", boom)
    assert seed_mod.seed_admin_user("a@b.c", "secret") == "exists"


def test_seed_admin_requires_creds():
    with pytest.raises(RuntimeError, match="LANGFUSE_ADMIN"):
        seed_mod.seed_admin_user("", "")


def test_wait_project_api_waits_for_db_then_succeeds(monkeypatch):
    hits = {"db": 0, "api": 0}

    def db(_pk: str) -> bool:
        hits["db"] += 1
        return hits["db"] >= 2

    def req(*_a, **_k):
        hits["api"] += 1
        return {"data": []}

    monkeypatch.setattr(seed_mod, "DATABASE_URL", "postgres://x")
    monkeypatch.setattr(seed_mod, "project_key_in_db", db)
    monkeypatch.setattr(seed_mod, "_request", req)
    monkeypatch.setattr(seed_mod.time, "sleep", lambda *_a, **_k: None)
    seed_mod.wait_project_api(
        {"id": "p", "publicKey": "pk", "secretKey": "sk"},
        attempts=5,
    )
    assert hits["db"] >= 2
    assert hits["api"] == 1


def test_wait_project_api_flushes_valkey_on_401(monkeypatch):
    flushed: list[str] = []

    def req(*_a, **_k):
        if not flushed:
            raise RuntimeError("GET /api/public/llm-connections -> 401: invalid")
        return {"data": []}

    monkeypatch.setattr(seed_mod, "DATABASE_URL", "postgres://x")
    monkeypatch.setattr(seed_mod, "project_key_in_db", lambda *_a, **_k: True)
    monkeypatch.setattr(seed_mod, "invalidate_api_key_cache", lambda sk: flushed.append(sk) or True)
    monkeypatch.setattr(seed_mod, "_request", req)
    monkeypatch.setattr(seed_mod.time, "sleep", lambda *_a, **_k: None)
    seed_mod.wait_project_api(
        {"id": "p", "publicKey": "pk", "secretKey": "sk-lf-x"},
        attempts=5,
    )
    assert flushed == ["sk-lf-x"]


def test_invalidate_api_key_cache_uses_fast_hash(monkeypatch):
    deleted: list[str] = []
    monkeypatch.setattr(seed_mod, "LANGFUSE_SALT", "salt")
    monkeypatch.setattr(seed_mod, "valkey_del", lambda key: deleted.append(key) or True)
    assert seed_mod.invalidate_api_key_cache("sk-lf-x")
    assert deleted == [f"api-key:{fast_hashed_secret_key('sk-lf-x', 'salt')}"]


def test_fast_hashed_secret_key_is_stable():
    first = fast_hashed_secret_key("sk-lf-x", "salt")
    second = fast_hashed_secret_key("sk-lf-x", "salt")
    assert first == second
    assert first != fast_hashed_secret_key("sk-lf-x", "other")
    assert display_secret_key("sk-lf-abcdef1234") == "sk-lf-...1234"
