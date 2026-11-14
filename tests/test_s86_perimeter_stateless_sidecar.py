"""S-86: a stateless (zero-DB) sidecar wrap holds no database at all (live).

Applies to every runtime agent wrapped statelessly (no DB, and tenant B cannot reach tenant A's threads
or runs through the agents host): on a profile=perimeter platform (where
`zelkor deploy` always does this) or with `--egress-only` on full. Needs KUBECONTEXT and
ZELKOR_RUNTIME_GRAPHS; skips when none of those agents is stateless. What the runtime container
can reach on its own (no credentials, no public egress, no model without the sidecar) is S-75,
which runs against the same agents.
"""
from __future__ import annotations

import json

import pytest

from tests.helpers.kube import kubectl_run
from tests.helpers.runtime_agents import deployment, require_kube, runtime_graphs


def _sidecar_env(spec: dict) -> dict[str, str]:
    (sidecar,) = [c for c in spec["containers"] if c["name"] == "sidecar"]
    return {e["name"]: e.get("value") for e in sidecar.get("env") or []}


def test_stateless_sidecar_has_no_db_and_no_migrate():
    require_kube()
    checked = []
    for graph in runtime_graphs():
        res = kubectl_run(["get", deployment(graph), "-o", "json"])
        assert res.returncode == 0, res.stderr
        spec = json.loads(res.stdout)["spec"]["template"]["spec"]
        env = _sidecar_env(spec)
        if env.get("ZELKOR_SIDECAR_STORE") != "memory":
            continue
        assert not spec.get("initContainers"), f"{graph}: stateless sidecar must have no migrate init-container"
        assert "DATABASE_URL" not in env, graph
        checked.append(graph)
    if not checked:
        pytest.skip("no stateless-wrapped runtime agent among ZELKOR_RUNTIME_GRAPHS")


def _status(exc: BaseException) -> int:
    resp = getattr(exc, "response", None)
    return int(getattr(resp, "status_code", 0) or getattr(exc, "status_code", 0) or 0)


def test_tenants_cannot_reach_each_others_threads_and_runs():
    """S-86 / P1 on the in-memory store: tenant B gets 404 for tenant A's thread, its state and
    history, and for starting a run on it (nothing executes); B's search never lists it."""
    from tests.helpers.runtime_agents import client, run, tenant_token

    graph = runtime_graphs()[0]
    a, b = tenant_token("tenant-a"), tenant_token("tenant-b")
    thread, _ = run(graph, a, "Reply with one word: ok")
    owner = client(graph, a)
    assert owner.threads.get(thread)["thread_id"] == thread, "positive control: A reads its own thread"
    intruder = client(graph, b)
    msg = {"messages": [{"role": "human", "content": "Reply with one word: ok"}]}
    for label, call in (("threads.get", lambda: intruder.threads.get(thread)),
                        ("threads.get_state", lambda: intruder.threads.get_state(thread)),
                        ("threads.get_history", lambda: intruder.threads.get_history(thread)),
                        ("runs.wait on A's thread", lambda: intruder.runs.wait(thread, graph, input=msg))):
        with pytest.raises(Exception) as exc:
            call()
        assert _status(exc.value) == 404, (label, repr(exc.value)[:200])
    found = [t.get("thread_id") for t in intruder.threads.search(limit=100)]
    assert thread not in found, "tenant B's search returned tenant A's thread"
    state = owner.threads.get_state(thread)
    assert "Reply with one word" in json.dumps(state, default=str), "A's thread lost its own state"
