"""CE-19g: upgrade/rollback and retry-storm gate logic (offline; the live run is upgrade-gates.yml)."""
from __future__ import annotations

import json
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
REL = ROOT / "scripts" / "release"
sys.path.insert(0, str(REL))

import ce_tags  # noqa: E402
import gateway_memory as gm  # noqa: E402
import loadgen  # noqa: E402
import mock_llm  # noqa: E402

THRESHOLDS = json.loads((REL / "gate-thresholds.json").read_text())
WORKFLOW = ROOT / ".github" / "workflows" / "upgrade-gates.yml"


# --- N-1 tag -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tags, current, want",
    [
        (["v2.4.5-ce", "v2.4.6-ce", "v2.10.0-ce", "v2.9.1-ce"], "v2.10.0-ce", "v2.9.1-ce"),
        (["v2.4.5-ce", "v2.4.6-ce", "v1.0.0", "v2.4.7-rc1-ce"], "v2.4.6-ce", "v2.4.5-ce"),
        (["v2.4.5-ce"], "v2.4.6-ce", "v2.4.5-ce"),  # dispatched before the tag exists locally
    ],
)
def test_previous_ce_tag(tags, current, want):
    assert ce_tags.previous(tags, current) == want


def test_no_previous_tag_is_an_error():
    with pytest.raises(ValueError):
        ce_tags.previous(["v2.4.6-ce"], "v2.4.6-ce")
    with pytest.raises(ValueError):
        ce_tags.previous(["v2.4.5-ce"], "main")


# --- mock provider + load generator ---------------------------------------------------------


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def mock_server():
    port = _free_port()
    server = mock_llm.make_server("127.0.0.1", port)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


def _post(url, model):
    import urllib.request

    req = urllib.request.Request(f"{url}/v1/chat/completions", method="POST",
                                 data=json.dumps({"model": model, "messages": []}).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_mock_provider_ok_and_always_fail(mock_server):
    status, body = _post(mock_server, "vllm/ok")
    assert status == 200 and body["choices"][0]["message"]["content"]
    status, body = _post(mock_server, "vllm/fail")
    assert status == 500 and "error" in body


def test_loadgen_counts_zero_failures_against_healthy_provider(mock_server):
    s = loadgen.run(url=f"{mock_server}/v1/chat/completions", host="ai.example", key="k", model="ok",
                    rps=20, duration=1.0)
    assert s["sent"] >= 10 and s["ok"] == s["sent"]
    assert s["non_2xx"] == 0 and s["conn_errors"] == 0
    assert loadgen.check(s, max_failed=0, max_ok=None) == []


def test_loadgen_counts_non_2xx_and_retries(mock_server):
    s = loadgen.run(url=f"{mock_server}/v1/chat/completions", host="", key="", model="fail",
                    rps=10, duration=0.5, retries=2)
    assert s["ok"] == 0 and s["non_2xx"] == s["sent"] > 0
    assert s["attempts"] == 3 * s["sent"]
    assert s["statuses"].get("500") == s["attempts"]
    assert loadgen.check(s, max_failed=0, max_ok=None)  # failures fail the upgrade gate
    assert loadgen.check(s, max_failed=None, max_ok=0) == []  # but are the storm's premise


def test_loadgen_counts_connection_errors():
    s = loadgen.run(url=f"http://127.0.0.1:{_free_port()}/v1/chat/completions", host="", key="",
                    model="ok", rps=10, duration=0.3, timeout=1)
    assert s["sent"] > 0 and s["conn_errors"] == s["sent"]
    assert loadgen.check(s, max_failed=0, max_ok=None)


def test_loadgen_stops_on_until_file(mock_server, tmp_path):
    stop = tmp_path / "stop"
    threading.Timer(0.5, stop.touch).start()
    started = time.monotonic()
    s = loadgen.run(url=f"{mock_server}/v1/chat/completions", host="", key="", model="ok", rps=10,
                    until_file=stop, duration=30)
    assert time.monotonic() - started < 5 and s["sent"] > 0


def test_no_requests_is_not_a_pass():
    empty = {"sent": 0, "ok": 0, "non_2xx": 0, "conn_errors": 0}
    assert loadgen.check(empty, max_failed=0, max_ok=None)


# --- Envoy dataplane memory -----------------------------------------------------------------

SUMMARY = {
    "pods": [
        {"podRef": {"name": "envoy-zelkor-abc", "namespace": "envoy-gateway-system"},
         "containers": [{"name": "envoy", "memory": {"workingSetBytes": 100 * 2**20}},
                        {"name": "shutdown-manager", "memory": {"workingSetBytes": 10 * 2**20}}]},
        {"podRef": {"name": "other", "namespace": "kube-system"},
         "containers": [{"name": "envoy", "memory": {"workingSetBytes": 999 * 2**20}}]},
    ]
}


def test_working_set_from_kubelet_summary():
    got = gm.working_sets(SUMMARY, namespace="envoy-gateway-system", pods={"envoy-zelkor-abc"})
    assert got == {("envoy-zelkor-abc", "envoy"): 100 * 2**20,
                   ("envoy-zelkor-abc", "shutdown-manager"): 10 * 2**20}


def _series(values_mib, interval=15, container="envoy"):
    return [gm.Sample(i * interval, "envoy-zelkor-abc", container, int(v * 2**20)) for i, v in enumerate(values_mib)]


GATE = {"container": "envoy", "envoy_memory_ceiling_mib": 384, "max_growth_pct": 15,
        "warmup_seconds": 60, "window_seconds": 120}


def test_flat_memory_under_ceiling_passes():
    ok, report = gm.analyze(_series([100 + (i % 3) for i in range(60)]), GATE)
    assert ok, report
    assert report["max_mib"] < 384


def test_memory_over_ceiling_fails():
    ok, report = gm.analyze(_series([100] * 30 + [400] + [100] * 29), GATE)
    assert not ok and "ceiling" in report["reason"]


def test_memory_growth_fails_even_under_ceiling():
    ok, report = gm.analyze(_series([100 + i * 2 for i in range(60)]), GATE)
    assert not ok and "growth" in report["reason"]


def test_too_few_samples_is_not_a_pass():
    ok, report = gm.analyze(_series([100] * 5), GATE)
    assert not ok and "samples" in report["reason"]


def test_other_containers_do_not_gate():
    samples = _series([100] * 60) + _series([900] * 60, container="shutdown-manager")
    ok, _ = gm.analyze(samples, GATE)
    assert ok


# --- published thresholds + thin workflow ---------------------------------------------------


def test_thresholds_are_published_in_one_file():
    storm = THRESHOLDS["retry_storm"]
    assert storm["duration_seconds"] == 1800
    assert storm["envoy_memory_ceiling_mib"] > 0
    assert THRESHOLDS["upgrade_rollback"]["max_failed_requests"] == 0


def test_storm_stays_under_the_kind_rate_limit():
    """Failures must reach the provider, not stop at the /v1 429 safety net."""
    rpm = yaml.safe_load((ROOT / "profiles/values-local-perimeter.yaml").read_text())[
        "workspace"]["models"]["rateLimit"]["requestsPerMinute"]
    storm = THRESHOLDS["retry_storm"]
    assert storm["rps"] * (1 + storm["client_retries"]) * 60 < rpm
    assert THRESHOLDS["upgrade_rollback"]["rps"] * 60 < rpm


def _wf() -> dict:
    data = yaml.safe_load(WORKFLOW.read_text())
    data["on"] = data.pop(True, data.get("on"))
    return data


def test_gates_run_after_release_and_on_dispatch():
    on = _wf()["on"]
    assert on["workflow_run"] == {"workflows": ["release"], "types": ["completed"]}
    assert "tag" in on["workflow_dispatch"]["inputs"]


def test_gate_jobs_are_thin_and_call_scripts():
    jobs = _wf()["jobs"]
    runs = {name: " ".join(s.get("run", "") for s in job["steps"]) for name, job in jobs.items()}
    assert "scripts/release/upgrade_gate.sh" in runs["upgrade-rollback"]
    assert "scripts/release/retry_storm_gate.sh" in runs["retry-storm"]
    for name in ("upgrade-rollback", "retry-storm"):
        assert all(len(s.get("run", "").splitlines()) <= 3 for s in jobs[name]["steps"]), name
    assert jobs["retry-storm"]["timeout-minutes"] >= 45


@pytest.mark.skipif(shutil.which("shellcheck") is None, reason="shellcheck not installed")
def test_gate_scripts_shellcheck_clean():
    scripts = [str(REL / n) for n in ("upgrade_gate.sh", "retry_storm_gate.sh", "lib-gates.sh")]
    r = subprocess.run(["shellcheck", "-x", *scripts], capture_output=True, text=True, cwd=REL)
    assert r.returncode == 0, r.stdout


def test_gate_scripts_pass_explicit_kube_context():
    """kubectl/helm only through kube()/hlm(), which name the context (never the default one)."""
    import re

    lib = (REL / "lib-gates.sh").read_text()
    assert 'kube() { kubectl --context "$GATE_CTX" "$@"; }' in lib
    assert 'hlm() { helm --kube-context "$GATE_CTX" "$@"; }' in lib
    for name in ("upgrade_gate.sh", "retry_storm_gate.sh", "lib-gates.sh"):
        for line in (REL / name).read_text().splitlines():
            code = line.split("#", 1)[0]
            if re.search(r"(^|[\s|;(])(kubectl|helm)\s", code) and not code.lstrip().startswith(("kube()", "hlm()")):
                raise AssertionError(f"{name}: bare kubectl/helm: {line}")
    assert '"kubectl", "--context", context' in (REL / "gateway_memory.py").read_text()
