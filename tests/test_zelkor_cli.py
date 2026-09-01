"""CLI unit tests: env file, init, shape detection, paid fail-closed (no cluster)."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli" / "src"))
sys.path.insert(0, str(ROOT / "images" / "aegra-deep"))

from zelkor.detect import DetectError, customer_dockerfile, detect, should_attach_as_default  # noqa: E402
from zelkor.envfile import Env, add_env, resolve_env  # noqa: E402
from zelkor.main import UPGRADE, PlatformInfo, auth_values, default_llm_model_from, in_cluster_openai_base_url, main, merge_extra_backends  # noqa: E402


def test_detect_deploy_first(tmp_path):
    (tmp_path / "agent.json").write_text('{"name": "desk"}', encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("hi\n", encoding="utf-8")
    shape = detect(tmp_path)
    assert shape.kind == "deploy-first"
    assert shape.graph_id == "desk"
    assert shape.mcp_inject is True


def test_detect_tools_json_disables_mode_b(tmp_path):
    (tmp_path / "agent.json").write_text('{"name": "agent"}', encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("hi\n", encoding="utf-8")
    (tmp_path / "tools.json").write_text(
        '[{"name": "acme", "url": "http://acme.svc:8080"}]',
        encoding="utf-8",
    )
    shape = detect(tmp_path)
    assert shape.mcp_inject is False
    assert shape.mcp_servers[0]["name"] == "acme"


def test_detect_graphs_map_wins(tmp_path):
    (tmp_path / "agent.json").write_text('{"name": "agent"}', encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("hi\n", encoding="utf-8")
    (tmp_path / "langgraph.json").write_text(
        '{"graphs": {"fraud": "./fraud.py:graph"}}',
        encoding="utf-8",
    )
    shape = detect(tmp_path)
    assert shape.kind == "code-first"
    assert shape.graph_id == "fraud"
    assert shape.mcp_inject is True


def test_detect_neither_errors(tmp_path):
    with pytest.raises(DetectError):
        detect(tmp_path)


def test_customer_dockerfile_from_deep_image():
    text = customer_dockerfile("ghcr.io/devopssquaddev/zelkor-aegra-deep:dev")
    assert text.startswith("FROM ghcr.io/devopssquaddev/zelkor-aegra-deep:dev")
    assert "COPY . /app/" in text
    assert "localhost" not in text


def test_detect_finserve_coder_is_deploy_first():
    root = ROOT / "examples" / "finserve" / "coder"
    shape = detect(root)
    assert shape.kind == "deploy-first"
    assert shape.graph_id == "finserve-coder"
    assert shape.wants_sandbox is True
    assert shape.mcp_inject is True
    assert not (root / "langgraph.json").exists()
    df = (ROOT / "images" / "example-finserve-coder" / "Dockerfile").read_text()
    assert "zelkor-aegra-deep" in df
    lg = json.loads((ROOT / "images" / "example-finserve-coder" / "langgraph.json").read_text())
    assert "zelkor_deep_factory.py:graph" in lg["graphs"]["finserve-coder"]
    assert "zelkor-example-finserve-coder" in (ROOT / "scripts" / "build-images.sh").read_text()
    assert "SANDBOX_WORKER_URLS" not in (ROOT / "examples" / "finserve" / "chart" / "values.yaml").read_text()
    assert "SANDBOX_WORKER_URLS" not in (ROOT / "examples" / "finserve" / "chart" / "values-local.yaml").read_text()


def test_should_attach_as_default_skips_existing_workers():
    assert should_attach_as_default([], "desk") is True
    assert should_attach_as_default(["desk-zelkor-agent-route"], "desk") is True
    assert should_attach_as_default(["finserve-desk-zelkor-agent-route"], "agent") is False


def test_merge_extra_backends_keeps_existing():
    merged = merge_extra_backends(
        [{"name": "one", "url": "http://one:8080"}],
        [{"name": "two", "url": "http://two:8080"}],
    )
    names = {r["name"] for r in merged}
    assert names == {"one", "two"}


def test_env_add_list_use(tmp_path):
    store = tmp_path / "envs.yaml"
    add_env(Env(name="staging", kube_context="staging-eks", namespace="zelkor"), store_path=store)
    env = resolve_env(name="staging", store_path=store)
    assert env.kube_context == "staging-eks"
    assert env.namespace == "zelkor"
    text = store.read_text(encoding="utf-8")
    assert "localhost" not in text
    assert "dev-key" not in text


def test_init_writes_deploy_first(tmp_path):
    assert main(["init", str(tmp_path)]) == 0
    agent = json.loads((tmp_path / "agent.json").read_text(encoding="utf-8"))
    assert agent["name"] == "agent"
    assert "servicenow" not in (tmp_path / "AGENTS.md").read_text().lower()
    assert not (tmp_path / "tools.json").exists()


def test_paid_verbs_fail_closed():
    for verb in ("login", "team", "budget", "audit", "whoami", "license"):
        code = main([verb])
        assert code == 2


def test_undeploy_logs_not_this_slice():
    assert main(["undeploy"]) == 2
    assert main(["logs"]) == 2


def test_version_without_env(capsys):
    assert main(["version"]) == 0
    out = capsys.readouterr().out
    assert "zelkor" in out


def test_doctor_status_mocked_kube(tmp_path, capsys):
    store = tmp_path / "envs.yaml"
    add_env(Env(name="local", kube_context="kind-zelkor", namespace="default"), store_path=store)

    def runner(argv, **kwargs):
        joined = " ".join(argv)
        stdout = ""
        if "helm" in argv and "list" in argv:
            stdout = json.dumps(
                [{"name": "zelkor-platform", "chart": "zelkor-platform-0.1.0", "status": "deployed"}]
            )
        elif "helm" in argv and "get" in argv and "values" in argv:
            stdout = "gateway:\n  hosts:\n    aegra: aegra.example\n"
        elif "get" in argv and "deploy" in argv:
            stdout = json.dumps(
                {
                    "items": [
                        {
                            "metadata": {
                                "name": "zelkor-platform-aegra",
                                "labels": {"app.kubernetes.io/component": "aegra"},
                            },
                            "spec": {
                                "template": {
                                    "spec": {
                                        "containers": [
                                            {
                                                "env": [
                                                    {"name": "DATABASE_URL", "value": "postgresql://x"},
                                                    {"name": "OPENAI_BASE_URL", "value": "http://gw/v1"},
                                                    {"name": "MCP_URL", "value": "http://mcp:8080"},
                                                    {"name": "OPENAI_API_KEY", "value": "k"},
                                                ]
                                            }
                                        ]
                                    }
                                }
                            },
                        }
                    ]
                }
            )
        elif "get" in argv and "svc" in argv:
            stdout = json.dumps({"items": []})
        elif "get" in argv and "httproute" in argv:
            stdout = json.dumps(
                {
                    "items": [
                        {
                            "metadata": {"name": "zelkor-platform-aegra-route"},
                            "spec": {"hostnames": ["aegra.example"], "parentRefs": [{"name": "zelkor-platform-gateway"}]},
                        }
                    ]
                }
            )
        return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

    assert main(["--store", str(store), "--env", "local", "doctor"], runner=runner) == 0
    out = capsys.readouterr().out
    assert "CE license: n/a" in out
    assert main(["--store", str(store), "--env", "local", "status"], runner=runner) == 0


def test_default_llm_model_from_nemo_when_aegra_env_empty():
    assert default_llm_model_from({}, {"guardrails": {"nemo": {"model": "gpt-oss:20b"}}}) == "gpt-oss:20b"
    assert default_llm_model_from({"DEFAULT_LLM_MODEL": "openai/gpt-4o-mini"}, {"guardrails": {"nemo": {"model": "gpt-oss:20b"}}}) == "openai/gpt-4o-mini"


def test_in_cluster_openai_base_url_uses_ai_gateway_service():
    def runner(argv, **_kwargs):
        stdout = json.dumps(
            {
                "items": [
                    {
                        "metadata": {"name": "zelkor-platform-ai-gateway"},
                        "spec": {"ports": [{"port": 80}]},
                    }
                ]
            }
        )
        return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

    env = Env(name="local", kube_context="kind-zelkor", namespace="default")
    assert in_cluster_openai_base_url(env, runner=runner) == "http://zelkor-platform-ai-gateway:80/v1"


def test_auth_values_copy_platform_wrap_auth():
    info = PlatformInfo(
        jwt_secret="cluster-jwt",
        auth_dev_tokens_enabled="true",
        auth_dev_token_prefix="dev:",
        auth_trust_tenant_header="true",
    )
    auth = auth_values(info)
    assert auth["jwtSecret"] == "cluster-jwt"
    assert auth["devTokens"]["enabled"] is True
    assert auth["devTokens"]["prefix"] == "dev:"
    assert auth["trustTenantHeader"] is True
    assert auth_values(PlatformInfo())["devTokens"]["enabled"] is False


def test_upgrade_text_constant():
    assert "Pro" in UPGRADE


def test_cli_deploy_overlay_has_no_sandbox_worker_urls():
    text = (ROOT / "cli" / "src" / "zelkor" / "main.py").read_text(encoding="utf-8")
    assert "SANDBOX_WORKER_URLS" not in text
    assert "sandbox_worker_urls" not in text
