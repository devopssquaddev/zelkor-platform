"""Runtime agents under restart, concurrency, timeouts and replicas (live; skips without its env).

ZELKOR_RUNTIME_GRAPHS selects agents. ZELKOR_CHAOS=1 allows deleting a runtime pod.
ZELKOR_TIMEOUT_GRAPH names an agent deployed with a short run timeout (ZELKOR_TIMEOUT_SECONDS).
ZELKOR_MULTI_REPLICA_GRAPH names an agent with two or more replicas.
"""
from __future__ import annotations

import os
import threading
import time
import uuid

import pytest

from tests.helpers.kube import kubectl_run
from tests.helpers.runtime_agents import (
    client, container_logs, deployment, require_kube, run_error, runtime_graphs, tenant_token,
)


def _final_text(out) -> str:
    for msg in reversed((out or {}).get("messages") or [] if isinstance(out, dict) else []):
        if msg.get("type") in ("ai", "assistant"):
            content = msg.get("content")
            return " ".join(str(p.get("text", "")) for p in content if isinstance(p, dict)) if isinstance(content, list) else str(content or "")
    return ""


def _graph(env: str) -> str:
    graph = os.environ.get(env, "").strip()
    return graph or runtime_graphs()[0]


def test_thread_survives_a_runtime_pod_restart():
    """History lives in the sidecar store; a new pod rebuilds the runtime session from it."""
    if os.environ.get("ZELKOR_CHAOS") != "1":
        pytest.skip("ZELKOR_CHAOS=1 not set (deletes a runtime pod)")
    require_kube()
    graph = _graph("ZELKOR_RECOVERY_GRAPH")
    c = client(graph, tenant_token("tenant-a"))
    word = f"zebra{uuid.uuid4().hex[:6]}"
    thread = c.threads.create()["thread_id"]
    out = c.runs.wait(thread, graph, input={"messages": [{"role": "human", "content": f"Remember the code word {word}. Reply only OK."}]})
    assert run_error(out) is None, run_error(out)
    kubectl_run(["delete", "pod", "-l", f"app.kubernetes.io/instance={graph}", "--wait=true"], timeout=180)
    assert kubectl_run(["rollout", "status", deployment(graph), "--timeout=300s"], timeout=320).returncode == 0
    out = c.runs.wait(thread, graph, input={"messages": [{"role": "human", "content": "What is the code word? Reply with the word only."}]})
    assert run_error(out) is None, run_error(out)
    assert word in _final_text(out).lower(), _final_text(out)[:200]


def test_concurrent_runs_queue_and_both_complete():
    """One active run per replica: a second run waits for the first instead of sharing its identity."""
    require_kube()
    graph = _graph("ZELKOR_CONCURRENCY_GRAPH")
    tokens = [tenant_token("tenant-a"), tenant_token("tenant-b")]
    since = time.time()
    results: dict[int, object] = {}

    def go(i):
        c = client(graph, tokens[i])
        thread = c.threads.create()["thread_id"]
        results[i] = c.runs.wait(thread, graph, input={"messages": [{"role": "human", "content": f"Reply only with the number {i}."}]})

    workers = [threading.Thread(target=go, args=(i,)) for i in (0, 1)]
    for w in workers:
        w.start()
    for w in workers:
        w.join(timeout=600)
    assert all(run_error(results.get(i)) is None and i in results for i in (0, 1)), results
    # Never more than one active run at a time in this window (sidecar run start/end log events).
    window = f"{int(time.time() - since) + 30}s"
    active = peak = 0
    for line in container_logs(deployment(graph), "sidecar", since=window).splitlines():
        if '"message": "run start"' in line:
            active += 1
            peak = max(peak, active)
        elif '"message": "run end"' in line:
            active = max(0, active - 1)
    assert peak <= 1, f"{peak} runs active at once"


def test_run_timeout_ends_a_long_run():
    graph = os.environ.get("ZELKOR_TIMEOUT_GRAPH", "").strip()
    if not graph:
        pytest.skip("ZELKOR_TIMEOUT_GRAPH not set")
    limit = int(os.environ.get("ZELKOR_TIMEOUT_SECONDS", "30"))
    c = client(graph, tenant_token("tenant-a"))
    thread = c.threads.create()["thread_id"]
    started = time.monotonic()
    out = c.runs.wait(thread, graph, input={"messages": [{"role": "human", "content":
        f"Call sandbox__execute_python once with timeout 300 and code: import time; time.sleep({limit * 4}); print(1)"}]})
    elapsed = time.monotonic() - started
    assert run_error(out) is not None, "a run past its timeout must end with an error"
    assert elapsed < limit + 60, f"run took {elapsed:.0f}s with a {limit}s timeout"


def test_any_replica_serves_a_thread():
    graph = os.environ.get("ZELKOR_MULTI_REPLICA_GRAPH", "").strip()
    if not graph:
        pytest.skip("ZELKOR_MULTI_REPLICA_GRAPH not set")
    require_kube()
    ready = kubectl_run(["get", deployment(graph), "-o", "jsonpath={.status.readyReplicas}"]).stdout.strip()
    assert int(ready or 0) >= 2, f"{graph} has {ready} ready replicas"
    c = client(graph, tenant_token("tenant-a"))
    thread = c.threads.create()["thread_id"]
    for i in range(4):
        out = c.runs.wait(thread, graph, input={"messages": [{"role": "human", "content": f"Turn {i}: reply only OK."}]})
        assert run_error(out) is None, (i, run_error(out))
    humans = [m for m in (out or {}).get("messages") or [] if m.get("type") == "human"]
    assert len(humans) == 4, f"history lost across replicas: {len(humans)} human turns"
