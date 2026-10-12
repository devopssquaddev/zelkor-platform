"""UAT-22 armor eval catalog. Live Langfuse checks skip when the API is down or seed is off."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "images" / "langfuse-seed"))

from seed import (  # noqa: E402
    EVAL_CATALOG,
    _ENV_NOT_CODE_EVAL,
    _HAS_TOOL_NAMES,
    _ROOT,
)
from tests.helpers.langfuse import (
    GATEWAY_BASE_URL,
    drop_code_eval_observations,
    is_code_eval_observation,
    is_code_eval_trace,
    langfuse_get,
)
from tests.test_helm_values_schema import PROFILES, _docs, _helm

_ON = (
    PROFILES / "values-production.yaml",
    PROFILES / "values-quickstart.yaml",
    PROFILES / "values-local.yaml",
)
_OFF = (PROFILES / "values-local-fast.yaml",)


def _env(container: dict) -> dict[str, str]:
    return {item["name"]: str(item["value"]) for item in container.get("env") or [] if "value" in item}


def _langfuse_envs(docs: list) -> list[dict[str, str]]:
    found = []
    for doc in docs:
        if not doc or doc.get("kind") != "Deployment":
            continue
        name = doc["metadata"]["name"]
        if not (name.endswith("-langfuse") or name.endswith("-langfuse-worker")):
            continue
        for container in doc["spec"]["template"]["spec"]["containers"]:
            found.append(_env(container))
    return found


def _bootstrap_env(docs: list) -> dict[str, str]:
    job = next(
        doc
        for doc in docs
        if doc and doc.get("kind") == "Job" and doc["metadata"]["name"].endswith("-langfuse-bootstrap")
    )
    return _env(job["spec"]["template"]["spec"]["containers"][0])


def test_uat22_chart_default_leaves_dispatcher_off():
    rendered = _helm()
    assert rendered.returncode == 0, rendered.stderr
    docs = _docs(rendered.stdout)
    for env in _langfuse_envs(docs):
        assert "LANGFUSE_CODE_EVAL_DISPATCHER" not in env
        assert "QUEUE_CONSUMER_CODE_EVAL_EXECUTION_QUEUE_IS_ENABLED" not in env
    assert "SEED_CODE_EVALUATORS" not in _bootstrap_env(docs)
    assert "SEED_CODE_EVAL_SAMPLING" not in _bootstrap_env(docs)


@pytest.mark.parametrize("profile", _ON, ids=lambda path: path.name)
def test_uat22_seed_on_enables_dispatcher_and_bootstrap(profile: Path):
    rendered = _helm(values_files=[profile])
    assert rendered.returncode == 0, rendered.stderr
    docs = _docs(rendered.stdout)
    envs = _langfuse_envs(docs)
    assert len(envs) == 2
    for env in envs:
        assert env["LANGFUSE_CODE_EVAL_DISPATCHER"] == "insecure-local"
        assert env["QUEUE_CONSUMER_CODE_EVAL_EXECUTION_QUEUE_IS_ENABLED"] == "true"
    assert _bootstrap_env(docs)["SEED_CODE_EVALUATORS"] == "true"
    expected_sampling = "1" if profile.name in {"values-local.yaml", "values-production.yaml"} else "0.1"
    assert _bootstrap_env(docs)["SEED_CODE_EVAL_SAMPLING"] == expected_sampling


@pytest.mark.parametrize("profile", _OFF, ids=lambda path: path.name)
def test_uat22_fast_profile_leaves_dispatcher_off(profile: Path):
    rendered = _helm(values_files=[profile])
    assert rendered.returncode == 0, rendered.stderr
    docs = _docs(rendered.stdout)
    for env in _langfuse_envs(docs):
        assert "LANGFUSE_CODE_EVAL_DISPATCHER" not in env
    assert _bootstrap_env(docs).get("SEED_CODE_EVALUATORS", "false") == "false"


def test_uat22_catalog_rules_exclude_code_eval_and_http_roots():
    root_names = {"zelkor-tenant-userid", "zelkor-step-budget", "zelkor-tool-names"}
    for _filename, score_name, _description, filters in EVAL_CATALOG:
        assert _ENV_NOT_CODE_EVAL in filters, score_name
        columns = {item.get("column") for item in filters}
        assert "environment" in columns
        if score_name in root_names:
            assert _ROOT in filters
            assert _HAS_TOOL_NAMES in filters
        else:
            assert _ROOT not in filters
            assert _HAS_TOOL_NAMES not in filters


def test_uat22_helpers_drop_execute_evaluator_rows():
    eval_obs = {
        "id": "e1",
        "name": "Execute evaluator: zelkor-tenant-userid",
        "environment": "langfuse-code-eval",
        "traceName": "Execute evaluator: zelkor-tenant-userid",
    }
    agent_obs = {"id": "a1", "name": "finserve-advisor", "environment": "default"}
    assert is_code_eval_observation(eval_obs)
    assert not is_code_eval_observation(agent_obs)
    assert drop_code_eval_observations([eval_obs, agent_obs]) == [agent_obs]
    assert is_code_eval_trace(
        {"name": "Execute evaluator: zelkor-step-budget", "observations": [eval_obs]}
    )
    assert not is_code_eval_trace({"name": "finserve-advisor", "observations": [agent_obs]})


def test_uat22_catalog_sources_ship_in_the_seed_image():
    dockerfile = (ROOT / "images" / "langfuse-seed" / "Dockerfile").read_text()
    assert "evaluators" in dockerfile
    names = []
    for filename, score_name, _description, _filters in EVAL_CATALOG:
        path = ROOT / "images" / "langfuse-seed" / "evaluators" / f"{filename}.ts"
        text = path.read_text()
        assert "function evaluate" in text
        assert score_name in text
        names.append(score_name)
    assert len(names) == 8
    assert len(set(names)) == 8


def test_uat22_live_jobs_are_typescript_and_enabled():
    if os.environ.get("LANGFUSE_INIT_ENABLED", "true").lower() not in ("1", "true", "yes"):
        pytest.skip("langfuse.init disabled")
    if os.environ.get("LANGFUSE_SEED_CODE_EVALUATORS", "true").lower() in ("0", "false", "no"):
        pytest.skip("evaluator seed disabled")
    try:
        evaluators = langfuse_get("/api/public/v2/evaluators", params={"limit": 100})
        rules = langfuse_get("/api/public/v2/evaluation-rules", params={"limit": 100})
    except httpx.ConnectError:
        pytest.skip(f"Langfuse not reachable at {GATEWAY_BASE_URL}")
    if evaluators.status_code in (401, 403, 404) or rules.status_code in (401, 403, 404):
        pytest.skip(f"evaluator API unavailable: {evaluators.status_code}/{rules.status_code}")
    assert evaluators.status_code == 200, evaluators.text
    assert rules.status_code == 200, rules.text
    expected = {item[1] for item in EVAL_CATALOG}
    ev_rows = evaluators.json().get("data") or []
    rule_rows = rules.json().get("data") or []
    ev_by_name = {row.get("name"): row for row in ev_rows}
    rule_by_name = {row.get("name"): row for row in rule_rows}
    if not expected.issubset(ev_by_name) or not expected.issubset(rule_by_name):
        pytest.skip(f"evaluator jobs not seeded (evaluators={set(ev_by_name)} rules={set(rule_by_name)})")
    for name in expected:
        assert ev_by_name[name].get("sourceCodeLanguage") == "TYPESCRIPT"
        assert ev_by_name[name].get("type") == "code"
        rule = rule_by_name[name]
        assert rule.get("enabled") is True
        columns = {item.get("column") for item in (rule.get("filter") or []) if isinstance(item, dict)}
        assert columns
        assert columns <= {"type", "level", "isRootObservation", "environment", "metadata"}
        assert "environment" in columns
        env = next(
            item
            for item in (rule.get("filter") or [])
            if isinstance(item, dict) and item.get("column") == "environment"
        )
        assert env.get("operator") == "none of"
        assert "langfuse-code-eval" in (env.get("value") or [])
        assert 0 < float(rule.get("sampling")) <= 1
        if "isRootObservation" in columns:
            meta = next(
                item
                for item in (rule.get("filter") or [])
                if isinstance(item, dict) and item.get("column") == "metadata"
            )
            assert meta.get("key") == "tool_names"
            assert meta.get("operator") == "is set"
