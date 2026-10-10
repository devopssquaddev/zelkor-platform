"""Live LR-1–LR-6. Skipped unless the example release and tokens are present."""
from __future__ import annotations

import json
import os
import subprocess
import time

import pytest

from redline_e2e import RULE_A, RULE_B, TENANT_A, TENANT_B, run_review
from tests.helpers.langfuse import (
    unexpected_error_observations,
    wait_for_traces,
    trace_detail,
    trace_observations,
)

UNLIMITED = "The provider accepts unlimited liability for all claims."
NET90 = "Fees are due net 90 days after the invoice date."


def _contract_governing_law() -> str:
    from pathlib import Path
    import sys

    files = Path(__file__).resolve().parents[1] / "chart" / "files"
    sys.path.insert(0, str(files))
    from clause_check import original_for_clause

    text = (files / "contract.txt").read_text(encoding="utf-8")
    return original_for_clause(text, "governing-law")


def _obs_names(observations: list) -> list[str]:
    rows = sorted(observations, key=lambda o: str(o.get("startTime") or ""))
    return [str(o.get("name") or "") for o in rows]


def _trace_for_thread(thread_id: str, timeout: float = 90.0, min_traces: int = 1) -> list:
    time.sleep(6)
    deadline = time.time() + timeout
    traces: list = []
    while time.time() < deadline:
        traces = wait_for_traces(
            lambda t: str(t.get("sessionId") or "") == thread_id,
            timeout=min(8.0, max(2.0, deadline - time.time())),
            session_id=thread_id or None,
        )
        if len(traces) >= min_traces:
            break
        time.sleep(2)
    if not traces:
        pytest.fail(f"no Langfuse trace for thread {thread_id}")
    observations: list = []
    for trace in traces:
        observations.extend(trace_observations(trace_detail(trace["id"])))
    return observations


def test_lr1_liability_cap_reject():
    result = run_review(clause_id="liability-cap", proposed=UNLIMITED, tenant_id=TENANT_A)
    suggestion = result["suggestion"]
    sandbox = result["sandbox"]
    assert sandbox.get("decision") == "reject"
    assert suggestion.get("decision") == sandbox.get("decision")
    assert RULE_A in (suggestion.get("matched_rule_ids") or [])

    observations = _trace_for_thread(result["thread_id"])
    names = " ".join(_obs_names(observations))
    for tool in ("object__read_text", "sandbox__execute_python", "qdrant__search_documents"):
        assert tool in names, f"missing {tool} in {names}"
    assert any("chat" in n.lower() or "openai" in n.lower() or "generation" in n.lower() or "ChatOpenAI" in n for n in _obs_names(observations)), (
        f"missing model call in {_obs_names(observations)}"
    )
    order = [n for n in _obs_names(observations) if n in {
        "object__read_text",
        "sandbox__execute_python",
        "qdrant__search_documents",
    }]
    assert order[:3] == [
        "object__read_text",
        "sandbox__execute_python",
        "qdrant__search_documents",
    ], order


def test_lr2_payment_terms_modify():
    result = run_review(clause_id="payment-terms", proposed=NET90, tenant_id=TENANT_A)
    sandbox = result["sandbox"]
    suggestion = result["suggestion"]
    assert sandbox.get("decision") == "modify"
    assert sandbox.get("fallback_days") == 45
    assert "net" in json.dumps(sandbox).lower()
    assert suggestion.get("decision") == "modify"
    assert "net 45" in str(suggestion.get("replacement") or "").lower()


def test_lr3_governing_law_accept():
    original = _contract_governing_law()
    result = run_review(clause_id="governing-law", proposed=original, tenant_id=TENANT_A)
    assert result["sandbox"].get("decision") == "accept"
    assert result["suggestion"].get("decision") == "accept"


def test_lr4_tenant_playbook_isolation():
    result = run_review(clause_id="liability-cap", proposed=UNLIMITED, tenant_id=TENANT_B)
    ids = result["suggestion"].get("matched_rule_ids") or []
    assert RULE_A not in ids
    assert RULE_B in ids


def test_lr5_followup_skips_sandbox():
    first = run_review(clause_id="liability-cap", proposed=UNLIMITED, tenant_id=TENANT_A)
    first_obs = _trace_for_thread(first["thread_id"])
    first_sandbox = sum(1 for n in _obs_names(first_obs) if n == "sandbox__execute_python")
    assert first_sandbox >= 1
    follow = run_review(
        clause_id="liability-cap",
        proposed="why that decision?",
        tenant_id=TENANT_A,
        thread_id=first["thread_id"],
    )
    text = json.dumps(follow["suggestion"] or follow["raw"], default=str).lower()
    assert follow["sandbox"].get("decision") == "reject" or "reject" in text
    assert "sandbox" not in text
    later = _trace_for_thread(first["thread_id"], min_traces=2)
    later_sandbox = sum(1 for n in _obs_names(later) if n == "sandbox__execute_python")
    assert later_sandbox == first_sandbox


def test_lr6_no_provider_key_and_clean_trace(kubeconfig, kubecontext):
    result = run_review(clause_id="liability-cap", proposed=UNLIMITED, tenant_id=TENANT_A)
    observations = _trace_for_thread(result["thread_id"])
    names = " ".join(_obs_names(observations))
    for tool in ("object__read_text", "sandbox__execute_python", "qdrant__search_documents"):
        assert tool in names
    assert not unexpected_error_observations(observations)

    env = os.environ.copy()
    env["KUBECONFIG"] = kubeconfig
    proc = subprocess.run(
        [
            "kubectl",
            "--kubeconfig",
            kubeconfig,
            "--context",
            kubecontext,
            "-n",
            os.environ.get("ZELKOR_NAMESPACE", "zelkor"),
            "get",
            "deploy",
            "legal-redline",
            "-o",
            "json",
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    if proc.returncode != 0:
        pytest.skip(f"legal-redline deploy not found: {proc.stderr[-200:]}")
    deploy = json.loads(proc.stdout)
    containers = deploy["spec"]["template"]["spec"]["containers"]
    env_vars = {row.get("name"): row.get("value") or "" for row in containers[0].get("env") or []}
    for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "AZURE_OPENAI_API_KEY"):
        value = env_vars.get(name, "")
        assert not value.startswith(("sk-", "sk-ant-", "sk-proj-")), name
        assert "openai.com" not in value.lower()
