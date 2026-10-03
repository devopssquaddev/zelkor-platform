"""CLI unit tests: env file, init, shape detection, paid fail-closed (no cluster)."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli" / "src"))
sys.path.insert(0, str(ROOT / "images" / "aegra-deep"))

from zelkor.detect import (  # noqa: E402
    DetectError,
    agent_deployment_name,
    customer_dockerfile,
    detect,
    should_attach_as_default,
)
from zelkor.envfile import Env, add_env, resolve_env  # noqa: E402
from zelkor.extra_backends import extra_backend_overlay_snippet, missing_extra_registrations  # noqa: E402
from zelkor.main import (  # noqa: E402
    UPGRADE,
    PlatformInfo,
    auth_values,
    default_llm_model_from,
    deploy_agent,
    deploy_from_values,
    fill_empty,
    helm_argv,
    in_cluster_openai_base_url,
    kube_argv,
    main,
    merge_catalog_values,
    _deploy_ready,
    _wait_agent_rollout,
)
from zelkor import token_cmd  # noqa: E402


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
    assert "COPY --chown=1000:1000 . /app/" in text
    assert "USER 1000" in text
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


def test_agent_deployment_name_matches_helm_fullname():
    assert agent_deployment_name("agent") == "agent-zelkor-agent"
    assert agent_deployment_name("desk") == "desk-zelkor-agent"
    assert agent_deployment_name("zelkor-agent") == "zelkor-agent"
    assert agent_deployment_name("my-zelkor-agent") == "my-zelkor-agent"


def test_missing_extra_registrations_detects_unregistered_tools():
    values = {"workspace": {"tools": {"extraBackends": [{"name": "one", "service": {"name": "one", "port": 8080}}]}}}
    missing = missing_extra_registrations(({"name": "two", "url": "http://two:8080"},), values)
    assert len(missing) == 1
    assert missing[0]["name"] == "two"
    snippet = extra_backend_overlay_snippet("acme", "http://acme-mcp:8080")
    assert "name: acme" in snippet
    assert "name: acme-mcp" in snippet


def test_deploy_agent_fails_when_tools_json_extra_not_on_platform(tmp_path):
    (tmp_path / "agent.json").write_text('{"name": "desk"}', encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("hi\n", encoding="utf-8")
    (tmp_path / "tools.json").write_text('[{"name": "acme", "url": "http://acme:8080"}]', encoding="utf-8")
    env = Env(name="local", kube_context="kind-zelkor", namespace="default")

    def runner(argv, **_kwargs):
        stdout = ""
        if "helm" in argv and "list" in argv:
            stdout = '[{"name": "zelkor-platform", "chart": "zelkor-platform-2.2.0", "status": "deployed"}]'
        elif "helm" in argv and "get" in argv and "values" in argv:
            stdout = "workspace:\n  tools:\n    extraBackends: []\n"
        return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

    with pytest.raises(RuntimeError, match="does not mutate the platform"):
        deploy_agent(
            root=tmp_path,
            env=env,
            push=False,
            skip_build=True,
            agent_chart=ROOT / "charts" / "zelkor-agent",
            platform_chart=ROOT / "charts" / "zelkor-platform",
            runner=runner,
        )


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


def test_undeploy_logs_helm_and_kubectl(tmp_path, capsys):
    store = tmp_path / "envs.yaml"
    add_env(Env(name="local", kube_context="kind-zelkor", namespace="default"), store_path=store)
    (tmp_path / "agent.json").write_text('{"name": "agent"}', encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("hi\n", encoding="utf-8")
    seen: list[list[str]] = []

    def runner(argv, **_kwargs):
        seen.append(list(argv))
        joined = " ".join(argv)
        stdout = ""
        if "helm" in argv and "list" in argv:
            stdout = json.dumps(
                [{"name": "zelkor-platform", "chart": "zelkor-platform-1.0.0", "status": "deployed"}]
            )
        elif "helm" in argv and "get" in argv and "values" in argv and "zelkor-platform" in argv:
            stdout = "gateway:\n  hosts:\n    agents: agents.example\n"
        elif "helm" in argv and "get" in argv and "values" in argv:
            stdout = "sharedRoute:\n  asDefault: true\n"
        elif "helm" in argv and "uninstall" in argv:
            stdout = ""
        elif "helm" in argv and "upgrade" in argv:
            stdout = ""
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
            stdout = json.dumps({"items": []})
        elif "logs" in argv:
            stdout = "ready\n"
        return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

    platform_chart = str(ROOT / "charts" / "zelkor-platform")
    assert (
        main(
            [
                "--store",
                str(store),
                "--env",
                "local",
                "--platform-chart",
                platform_chart,
                "undeploy",
                str(tmp_path),
            ],
            runner=runner,
        )
        == 0
    )
    joined = [" ".join(a) for a in seen]
    assert any("uninstall" in j and " agent " in f" {j} " for j in joined)
    assert any("attachDefaultRoute=true" in j for j in joined)
    out = capsys.readouterr().out
    assert json.loads(out.strip().splitlines()[-1])["restored_default"] is True

    seen.clear()
    assert (
        main(
            [
                "--store",
                str(store),
                "--env",
                "local",
                "logs",
                "--no-follow",
                "--tail",
                "20",
                str(tmp_path),
            ],
            runner=runner,
        )
        == 0
    )
    log_cmd = " ".join(seen[-1])
    assert "logs" in log_cmd
    assert "deployment/agent-zelkor-agent" in log_cmd
    assert "--tail" in log_cmd
    assert "-f" not in seen[-1]
    assert "ready" in capsys.readouterr().out


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
                [{"name": "zelkor-platform", "chart": "zelkor-platform-1.0.0", "status": "deployed"}]
            )
        elif "helm" in argv and "get" in argv and "values" in argv:
            stdout = "gateway:\n  hosts:\n    agents: agents.example\n"
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
                            "spec": {"hostnames": ["agents.example"], "parentRefs": [{"name": "zelkor-platform-gateway"}]},
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
    assert default_llm_model_from({}, {"aiGateway": {"defaultModel": "qwen3:8b"}}) == "qwen3:8b"
    assert default_llm_model_from({}, {"guardrails": {"nemo": {"model": "gpt-oss:20b"}}, "aiGateway": {"defaultModel": "qwen3:8b"}}) == "gpt-oss:20b"
    assert default_llm_model_from({}, {"langfuse": {"surfaces": {"llmConnection": {"models": ["gpt-oss:20b"]}}}}) == "gpt-oss:20b"


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


def test_auth_values_copy_platform_jwt_contract():
    info = PlatformInfo(
        jwt_issuer="https://issuer.example",
        jwt_audiences=["zelkor"],
        jwt_jwks_configmap="zelkor-platform-tenant-jwks",
        jwt_tenant_claims=["tenant_id", "sub"],
    )
    auth = auth_values(info)
    assert auth["issuer"] == "https://issuer.example"
    assert auth["audiences"] == ["zelkor"]
    assert auth["jwksConfigMap"] == "zelkor-platform-tenant-jwks"
    assert auth["tenantClaims"] == ["tenant_id", "sub"]


def test_upgrade_text_constant():
    assert "Pro" in UPGRADE


def test_deploy_agent_rejects_approval_threshold_on_ce(tmp_path):
    (tmp_path / "agent.json").write_text('{"name": "desk"}', encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("hi\n", encoding="utf-8")
    env = Env(name="prod", kube_context="k3s", namespace="zelkor")
    with pytest.raises(RuntimeError, match="Pro"):
        deploy_agent(
            root=tmp_path,
            env=env,
            push=False,
            skip_build=True,
            agent_chart=ROOT / "charts" / "zelkor-agent",
            platform_chart=ROOT / "charts" / "zelkor-platform",
            approval_threshold="0.5",
            runner=lambda *a, **k: SimpleNamespace(returncode=0, stdout="{}", stderr=""),
        )


def test_deploy_agent_requires_registry_off_kind(tmp_path, monkeypatch):
    (tmp_path / "agent.json").write_text('{"name": "desk"}', encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("hi\n", encoding="utf-8")
    monkeypatch.delenv("ZELKOR_IMAGE_REGISTRY", raising=False)
    env = Env(name="prod", kube_context="k3s", namespace="zelkor")
    with pytest.raises(RuntimeError, match="ZELKOR_IMAGE_REGISTRY"):
        deploy_agent(
            root=tmp_path,
            env=env,
            push=False,
            skip_build=True,
            agent_chart=ROOT / "charts" / "zelkor-agent",
            platform_chart=ROOT / "charts" / "zelkor-platform",
            runner=lambda *a, **k: SimpleNamespace(returncode=0, stdout="{}", stderr=""),
        )


def _discover_runner(captured: dict | None = None):
    captured = captured if captured is not None else {}

    def runner(argv, **_kwargs):
        if captured is not None and "upgrade" in argv and "--install" in argv:
            idx = argv.index("-f")
            captured["values"] = Path(argv[idx + 1]).read_text(encoding="utf-8")
            captured["argv"] = list(argv)
        stdout = ""
        if "helm" in argv and "list" in argv:
            stdout = json.dumps(
                [{"name": "zelkor-platform", "chart": "zelkor-platform-2.2.0", "status": "deployed"}]
            )
        elif "helm" in argv and "get" in argv and "values" in argv:
            stdout = "gateway:\n  hosts:\n    agents: agents.example.com\n"
        elif "get" in argv and "deploy" in argv and "-l" not in argv:
            stdout = json.dumps(
                {
                    "kind": "Deployment",
                    "metadata": {"generation": 1},
                    "spec": {"replicas": 1},
                    "status": {
                        "observedGeneration": 1,
                        "updatedReplicas": 1,
                        "availableReplicas": 1,
                    },
                }
            )
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
                                                    {"name": "OPENAI_API_KEY", "value": "cluster-consumer"},
                                                    {"name": "REDIS_URL", "value": "redis://valkey:6379"},
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
            stdout = json.dumps({"items": []})
        return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

    return runner


def test_merge_catalog_values_file_wins():
    file_values = {
        "graphId": "gpt-researcher",
        "runtimeClassName": "gvisor",
        "image": {"repository": "ghcr.io/devopssquaddev/zelkor-armored-gpt-researcher", "tag": "2.2.0"},
        "extraEnv": [{"name": "FOO", "value": "bar"}],
        "platform": {"releaseName": ""},
        "sharedRoute": {"host": ""},
    }
    discovered = {
        "platform": {"releaseName": "zelkor-platform", "consumerKey": "cluster-consumer"},
        "sharedRoute": {"host": "agents.example.com", "asDefault": True},
        "auth": {"issuer": "https://issuer.example"},
    }
    merged = merge_catalog_values(file_values, discovered)
    assert merged["graphId"] == "gpt-researcher"
    assert merged["runtimeClassName"] == "gvisor"
    assert merged["image"]["repository"].endswith("zelkor-armored-gpt-researcher")
    assert merged["extraEnv"] == [{"name": "FOO", "value": "bar"}]
    assert merged["platform"]["releaseName"] == "zelkor-platform"
    assert merged["sharedRoute"]["host"] == "agents.example.com"
    assert "asDefault" not in merged["sharedRoute"]
    assert merged["auth"]["issuer"] == "https://issuer.example"


def test_deploy_ready_false_on_progress_deadline_without_replicas():
    dep = {
        "kind": "Deployment",
        "metadata": {"generation": 2},
        "spec": {"replicas": 1},
        "status": {
            "observedGeneration": 2,
            "updatedReplicas": 0,
            "availableReplicas": 0,
            "conditions": [{"type": "Progressing", "status": "False", "reason": "ProgressDeadlineExceeded"}],
        },
    }
    assert _deploy_ready(dep) is False
    env = Env(name="local", kube_context="kind-zelkor", namespace="default")
    calls = {"n": 0}

    def runner(argv, **_kwargs):
        calls["n"] += 1
        if "pods" in argv:
            return SimpleNamespace(returncode=0, stdout='{"items":[]}', stderr="")
        if calls["n"] == 1:
            return SimpleNamespace(returncode=0, stdout=json.dumps(dep), stderr="")
        ready = dict(dep)
        ready["status"] = {
            "observedGeneration": 2,
            "updatedReplicas": 1,
            "availableReplicas": 1,
            "conditions": [{"type": "Progressing", "status": "True", "reason": "NewReplicaSetAvailable"}],
        }
        return SimpleNamespace(returncode=0, stdout=json.dumps(ready), stderr="")

    _wait_agent_rollout(env, "gpt-researcher", runner=runner, timeout_sec=5)
    assert calls["n"] >= 2


def test_kube_argv_sets_request_timeout():
    env = Env(name="local", kube_context="kind-zelkor", namespace="default")
    kube = kube_argv(env, "get", "ns")
    helm = helm_argv(env, "list", "-o", "json")
    assert kube[:3] == ["kubectl", "--request-timeout", "30s"]
    assert helm[:3] == ["helm", "--kube-context", "kind-zelkor"]
    assert "--request-timeout" not in helm
    assert "--context" in kube and "kind-zelkor" in kube


def test_fill_empty_keeps_set_values():
    assert fill_empty({"host": "mine"}, {"host": "theirs", "gatewayName": "gw"}) == {
        "host": "mine",
        "gatewayName": "gw",
    }


def test_deploy_from_values_skips_docker(tmp_path):
    values = tmp_path / "values.yaml"
    values.write_text(
        "\n".join(
            [
                "graphId: gpt-researcher",
                "runtimeClassName: gvisor",
                "image:",
                "  repository: ghcr.io/devopssquaddev/zelkor-armored-gpt-researcher",
                "  tag: '2.2.0'",
                "extraEnv: []",
                "platform:",
                "  releaseName: ''",
                "sharedRoute:",
                "  host: ''",
            ]
        ),
        encoding="utf-8",
    )
    env = Env(name="prod", kube_context="k3s", namespace="zelkor")
    captured: dict = {}
    result = deploy_from_values(
        values_path=values,
        env=env,
        agent_chart=ROOT / "charts" / "zelkor-agent",
        platform_chart=ROOT / "charts" / "zelkor-platform",
        runner=_discover_runner(captured),
    )
    assert result["graph_id"] == "gpt-researcher"
    assert result["release"] == "gpt-researcher"
    assert "docker" not in " ".join(captured.get("argv") or [])
    dumped = captured["values"]
    assert "gpt-researcher" in dumped
    assert "gvisor" in dumped
    assert "zelkor-armored-gpt-researcher" in dumped
    assert "agents.example.com" in dumped
    assert "zelkor-platform" in dumped
    assert "cluster-consumer" in dumped


def test_deploy_from_values_rejects_approval_threshold(tmp_path):
    values = tmp_path / "values.yaml"
    values.write_text(
        "graphId: gpt-researcher\nimage:\n  repository: ghcr.io/example/agent\n",
        encoding="utf-8",
    )
    env = Env(name="prod", kube_context="k3s", namespace="zelkor")
    with pytest.raises(RuntimeError, match="Pro"):
        deploy_from_values(
            values_path=values,
            env=env,
            agent_chart=ROOT / "charts" / "zelkor-agent",
            platform_chart=ROOT / "charts" / "zelkor-platform",
            approval_threshold="0.5",
            runner=lambda *a, **k: SimpleNamespace(returncode=0, stdout="{}", stderr=""),
        )


def test_cli_deploy_f_skips_docker_and_detect(tmp_path, capsys, caplog):
    store = tmp_path / "envs.yaml"
    add_env(Env(name="prod", kube_context="k3s", namespace="zelkor"), store_path=store)
    values = tmp_path / "values.yaml"
    values.write_text(
        "\n".join(
            [
                "graphId: gpt-researcher",
                "runtimeClassName: gvisor",
                "image:",
                "  repository: ghcr.io/devopssquaddev/zelkor-armored-gpt-researcher",
                "  tag: '2.2.0'",
            ]
        ),
        encoding="utf-8",
    )
    captured: dict = {}
    code = main(
        [
            "--store",
            str(store),
            "--env",
            "prod",
            "--chart",
            str(ROOT / "charts" / "zelkor-agent"),
            "--platform-chart",
            str(ROOT / "charts" / "zelkor-platform"),
            "deploy",
            "-f",
            str(values),
            str(tmp_path),
        ],
        runner=_discover_runner(captured),
    )
    assert code == 0
    assert "docker" not in " ".join(captured.get("argv") or [])
    out = capsys.readouterr().out
    assert "gpt-researcher" in out
    assert "discover platform" in caplog.text
    assert "helm upgrade --install" in caplog.text


def test_cli_deploy_overlay_has_no_sandbox_worker_urls():
    text = (ROOT / "cli" / "src" / "zelkor" / "main.py").read_text(encoding="utf-8")
    assert "SANDBOX_WORKER_URLS" not in text
    assert "sandbox_worker_urls" not in text


def test_token_mint_reads_issuer_audiences_and_ttl_from_cluster(monkeypatch, capsys):
    import base64

    import jwt as pyjwt

    from tests.helpers.jwt_keys import generate_rsa_keypair

    kp = generate_rsa_keypair("1")

    def fake_run(cmd, **_kwargs):
        target = " ".join(cmd)
        if " secret " in f" {target} " and "tenant-jwt-signing" in target:
            stdout = json.dumps(
                {
                    "data": {
                        "privateKey": base64.b64encode(kp.private_pem).decode(),
                        "kid": base64.b64encode(b"1").decode(),
                    }
                }
            )
        elif " configmap " in f" {target} " and "tenant-jwks" in target:
            stdout = json.dumps(
                {
                    "metadata": {"annotations": {"zelkor.io/token-ttl": "24h"}},
                    "data": {"jwks": json.dumps(kp.jwks)},
                }
            )
        elif " configmap " in f" {target} " and "tenant-jwt" in target and "tenant-jwks" not in target:
            stdout = json.dumps(
                {
                    "data": {
                        "AUTH_JWT_ISSUER": "https://local.zelkor.invalid",
                        "AUTH_JWT_AUDIENCES": json.dumps(["zelkor"]),
                    }
                }
            )
        else:
            return SimpleNamespace(returncode=1, stdout="", stderr=f"unexpected kubectl: {target}")
        return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr(token_cmd.subprocess, "run", fake_run)
    args = SimpleNamespace(
        release="zelkor-platform",
        namespace="default",
        kubeconfig="",
        context="",
        tenant="Bank_Alpha",
        issuer="",
        audience="",
        ttl="",
        out="",
    )
    monkeypatch.setenv("KUBECONTEXT", "kind-zelkor")
    monkeypatch.delenv("KUBE_CONTEXT", raising=False)
    assert token_cmd.cmd_token_mint(args) == 0
    token = capsys.readouterr().out.strip()
    assert token.startswith("eyJ")
    claims = pyjwt.decode(token, options={"verify_signature": False})
    assert claims["iss"] == "https://local.zelkor.invalid"
    assert claims["aud"] == ["zelkor"]
    assert claims["tenant_id"] == "Bank_Alpha"


def test_token_mint_uses_default_namespace_when_unset(monkeypatch):
    seen_ns: list[str] = []

    def fake_run(cmd, **_kwargs):
        if "-n" in cmd:
            seen_ns.append(cmd[cmd.index("-n") + 1])
        return SimpleNamespace(returncode=1, stdout="", stderr="fail")

    monkeypatch.setattr(token_cmd.subprocess, "run", fake_run)
    args = SimpleNamespace(
        release="zelkor-platform",
        namespace="",
        kubeconfig="",
        context="kind-zelkor",
        tenant="t",
        issuer="https://issuer.example",
        audience="zelkor",
        ttl="1h",
        out="",
    )
    with pytest.raises(RuntimeError):
        token_cmd.cmd_token_mint(args)
    assert seen_ns and seen_ns[0] == "default"
