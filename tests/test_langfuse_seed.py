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
    assert keep_mcp_tool("aigateway__call", extras)
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


def test_parse_extra_projects_requires_complete_entries():
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
    with pytest.raises(ValueError, match="requires id, publicKey, and secretKey"):
        parse_extra_projects(raw)
    assert parse_extra_projects("") == []
    with pytest.raises(ValueError, match="not valid JSON"):
        parse_extra_projects("not-json")


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
    assert "platform.telemetry.langfuse.init" not in raw
    assert "zelkor-dev-password" not in raw
    assert "databaseUrl:" not in raw


def test_helm_langfuse_otel_secret_from_init_keys():
    import subprocess

    root = Path(__file__).resolve().parents[1]
    chart = root / "charts/zelkor-platform"
    local = root / "profiles/values-local.yaml"
    try:
        proc = subprocess.run(
            [
                "helm",
                "template",
                "zelkor-platform",
                str(chart),
                "-f",
                str(local),
                "-s",
                "templates/langfuse/secret-langfuse-keys.yaml",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        pytest.skip("helm not installed")
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "name: zelkor-platform-langfuse-otel" in proc.stdout
    assert "OTEL_TARGETS: LANGFUSE" in proc.stdout
    assert "http://zelkor-platform-langfuse:3000" in proc.stdout
    assert "localhost" not in proc.stdout
    assert "dev-key" not in proc.stdout


def test_helm_langfuse_otel_secret_omitted_when_init_disabled():
    import subprocess

    root = Path(__file__).resolve().parents[1]
    chart = root / "charts/zelkor-platform"
    try:
        proc = subprocess.run(
            [
                "helm",
                "template",
                "zelkor-platform",
                str(chart),
                "--set",
                "platform.telemetry.langfuse.init.enabled=false",
                "--set",
                "postgresql.auth.password=test-pg-pass",
                "--set",
                "clickhouse.auth.password=test-ch-pass",
                "-s",
                "templates/langfuse/secret-langfuse-keys.yaml",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        pytest.skip("helm not installed")
    combined = (proc.stdout or "") + (proc.stderr or "")
    assert "zelkor-platform-langfuse-otel" not in combined


def test_helm_langfuse_init_generates_otel_secret_when_enabled():
    import subprocess

    root = Path(__file__).resolve().parents[1]
    chart = root / "charts/zelkor-platform"
    qs = root / "profiles/values-quickstart.yaml"
    try:
        proc = subprocess.run(
            [
                "helm",
                "template",
                "zelkor-platform",
                str(chart),
                "-f",
                str(qs),
                "--set",
                "postgresql.auth.password=test-pg-pass",
                "--set",
                "clickhouse.auth.password=test-ch-pass",
                "--set",
                "seaweedfs.auth.accessKey=testaccess",
                "--set",
                "seaweedfs.auth.secretKey=testsecretkey123456789012",
                "--set",
                "valkey.auth.password=test-valkey",
                "--set",
                "gateway.hosts.langfuse=langfuse.example.com",
                "--set",
                "gateway.hosts.agents=agents.example.com",
                "--set",
                "platform.telemetry.langfuse.nextauthUrl=https://langfuse.example.com",
                "--set",
                "platform.telemetry.langfuse.salt=salt",
                "--set",
                "platform.telemetry.langfuse.nextauthSecret=nextauth",
                "--set",
                "platform.telemetry.langfuse.encryptionKey=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
                "-s",
                "templates/langfuse/secret-langfuse-keys.yaml",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        pytest.skip("helm not installed")
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "name: zelkor-platform-langfuse-init" in proc.stdout
    assert "name: zelkor-platform-langfuse-otel" in proc.stdout
    assert "pk-lf-" in proc.stdout
    assert "sk-lf-" in proc.stdout


def test_helm_extra_projects_on_seed_job_and_nemo():
    import subprocess
    import tempfile

    root = Path(__file__).resolve().parents[1]
    chart = root / "charts/zelkor-platform"
    local = root / "profiles/values-local.yaml"
    extra_overlay = """
platform:
  telemetry:
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
                "templates/langfuse/job-bootstrap.yaml",
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
    monkeypatch.setattr(seed_mod, "_verify_admin_password", lambda e, p: True)
    assert seed_mod.seed_admin_user("a@b.c", "secret") == "exists"


def test_seed_admin_weak_password_fails(monkeypatch):
    monkeypatch.setattr(seed_mod, "_admin_exists_sql", lambda email: False)
    monkeypatch.setattr(
        seed_mod,
        "_signup",
        lambda e, p, n: (422, '{"message":{"name":"ZodError","message":"invalid password"}}'),
    )
    with pytest.raises(RuntimeError, match="signup failed 422"):
        seed_mod.seed_admin_user("a@b.c", "weak", "Admin")


def test_seed_admin_exists_sql(monkeypatch):
    monkeypatch.setattr(seed_mod, "_admin_exists_sql", lambda email: True)
    monkeypatch.setattr(seed_mod, "_verify_admin_password", lambda e, p: True)

    def boom(*_a, **_k):
        raise AssertionError("signup should not run")

    monkeypatch.setattr(seed_mod, "_signup", boom)
    assert seed_mod.seed_admin_user("a@b.c", "secret") == "exists"


def test_seed_admin_exists_sql_wrong_password(monkeypatch):
    monkeypatch.setattr(seed_mod, "_admin_exists_sql", lambda email: True)
    monkeypatch.setattr(seed_mod, "_verify_admin_password", lambda e, p: False)
    with pytest.raises(RuntimeError, match="public signup before bootstrap"):
        seed_mod.seed_admin_user("a@b.c", "secret")


def test_seed_admin_requires_creds():
    with pytest.raises(RuntimeError, match="LANGFUSE_ADMIN"):
        seed_mod.seed_admin_user("", "")


def test_wait_project_api_waits_for_db_then_succeeds(monkeypatch):
    hits = {"db": 0, "api": 0}

    def db(_pk: str, _pid: str) -> bool:
        hits["db"] += 1
        return hits["db"] >= 2

    def req(*_a, **_k):
        hits["api"] += 1
        return {"data": []}

    monkeypatch.setattr(seed_mod, "DATABASE_URL", "postgres://x")
    monkeypatch.setattr(seed_mod, "project_key_bound", db)
    monkeypatch.setattr(seed_mod, "INIT_SETTLE_SEC", 0)
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
    monkeypatch.setattr(seed_mod, "project_key_bound", lambda *_a, **_k: True)
    monkeypatch.setattr(seed_mod, "INIT_SETTLE_SEC", 0)
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
    monkeypatch.setattr(seed_mod, "VALKEY_HOST", "valkey")
    monkeypatch.setattr(seed_mod, "LANGFUSE_SALT", "salt")
    monkeypatch.setattr(seed_mod, "valkey_del", lambda key: deleted.append(key) or True)
    monkeypatch.setattr(seed_mod, "flush_all_api_key_cache", lambda: 0)
    assert seed_mod.invalidate_api_key_cache("sk-lf-x")
    assert deleted == [f"api-key:{fast_hashed_secret_key('sk-lf-x', 'salt')}"]


def test_invalidate_api_key_cache_falls_back_to_flush_all(monkeypatch):
    monkeypatch.setattr(seed_mod, "VALKEY_HOST", "valkey")
    monkeypatch.setattr(seed_mod, "LANGFUSE_SALT", "salt")
    monkeypatch.setattr(seed_mod, "valkey_del", lambda _key: False)
    monkeypatch.setattr(seed_mod, "flush_all_api_key_cache", lambda: 2)
    assert seed_mod.invalidate_api_key_cache("sk-lf-x")


def test_project_key_bound_delegates_without_project_id(monkeypatch):
    monkeypatch.setattr(seed_mod, "DATABASE_URL", "")
    assert not seed_mod.project_key_bound("pk", "")
    assert not seed_mod.project_key_bound("pk", "proj")


def test_valkey_keys_parses_api_key_hashes(monkeypatch):
    reply = b"*1\r\n$74\r\napi-key:e881d47e204e5c7d88b09908d2ee3b62f6f1a5c6cd219bdb03291fa33d5af776\r\n"
    monkeypatch.setattr(seed_mod, "VALKEY_HOST", "valkey")
    monkeypatch.setattr(seed_mod, "_valkey_roundtrip", lambda _parts: reply)
    keys = seed_mod.valkey_keys("api-key:*")
    assert keys == ["api-key:e881d47e204e5c7d88b09908d2ee3b62f6f1a5c6cd219bdb03291fa33d5af776"]


def test_fast_hashed_secret_key_is_stable():
    first = fast_hashed_secret_key("sk-lf-x", "salt")
    second = fast_hashed_secret_key("sk-lf-x", "salt")
    assert first == second
    assert first != fast_hashed_secret_key("sk-lf-x", "other")
    assert display_secret_key("sk-lf-abcdef1234") == "sk-lf-...1234"


def test_run_bootstrap_order(monkeypatch):
    order: list[str] = []

    monkeypatch.setattr(seed_mod, "wait_healthy", lambda: order.append("health"))
    monkeypatch.setattr(seed_mod, "SEED_ADMIN", True)
    monkeypatch.setattr(seed_mod, "seed_admin_user", lambda: order.append("admin"))
    monkeypatch.setattr(seed_mod, "SEED_INIT", True)
    monkeypatch.setattr(seed_mod, "seed_init_project_sql", lambda: order.append("init"))
    monkeypatch.setattr(
        seed_mod,
        "parse_extra_projects",
        lambda _raw: [{"id": "x", "name": "x", "publicKey": "pk-x", "secretKey": "sk-x"}],
    )
    monkeypatch.setattr(seed_mod, "seed_extra_projects", lambda: order.append("extras"))
    monkeypatch.setattr(seed_mod, "_armor_enabled", lambda: True)
    monkeypatch.setattr(seed_mod, "seed_armor", lambda _p: order.append("armor"))
    monkeypatch.setattr(seed_mod, "managed_projects", lambda: [{"id": "init"}])
    seed_mod.run_bootstrap()
    assert order == ["health", "admin", "init", "extras", "armor"]


def test_seed_init_project_sql_requires_keys(monkeypatch):
    monkeypatch.setattr(seed_mod, "SEED_INIT", True)
    monkeypatch.setattr(seed_mod, "DATABASE_URL", "postgres://x")
    monkeypatch.setattr(seed_mod, "ORG_ID", "org")
    monkeypatch.setattr(seed_mod, "LANGFUSE_SALT", "salt")
    monkeypatch.setattr(seed_mod, "PROJECT_ID", "")
    with pytest.raises(RuntimeError, match="LANGFUSE_PROJECT_ID"):
        seed_mod.seed_init_project_sql()


def test_helm_bootstrap_wait_init_on_aegra_when_init_enabled():
    import subprocess
    import tempfile

    root = Path(__file__).resolve().parents[1]
    chart = root / "charts/zelkor-platform"
    local = root / "profiles/values-local.yaml"
    try:
        proc = subprocess.run(
            [
                "helm",
                "template",
                "zelkor",
                str(chart),
                "-f",
                str(local),
                "-s",
                "templates/aegra/deployment.yaml",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        pytest.skip("helm not installed")
    assert proc.returncode == 0, proc.stderr or proc.stdout
    out = proc.stdout
    assert "wait-langfuse-bootstrap" in out
    assert "LANGFUSE_HOST" in out
    assert "/api/public/llm-connections" in out
    assert "envFrom:" in out
    assert "zelkor-zelkor-platform-langfuse-otel" in out
    assert "busybox:1.37" in out
    assert "kubectl" not in out
    assert "bitnami" not in out.lower()
    assert "langfuse-bootstrap-wait" not in out
