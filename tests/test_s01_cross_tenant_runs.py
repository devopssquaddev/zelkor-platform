"""S-01 (P1) L3: tenant B cannot read, join, stream, list or extend tenant A's thread and run.

Raw Agent Protocol over the Aegra front door (no SDK retries hiding a status). A's own reads are
the positive control, so a 404 for B is the tenant boundary, not a broken route."""
from __future__ import annotations

import os
import uuid

import httpx
import pytest

from tests.helpers.langgraph_client import _gateway_url, _request_headers

GRAPH = os.environ.get("AEGRA_WORKER_GRAPH_ID", "")
DENIED = (403, 404)


def _client(tenant: str, *, graph: str = "") -> httpx.Client:
    return httpx.Client(base_url=_gateway_url(), headers=_request_headers(tenant_id=tenant, graph_id=graph or None),
                        timeout=60.0)


@pytest.fixture(scope="module")
def a_run():
    if not GRAPH:
        pytest.skip("AEGRA_WORKER_GRAPH_ID not set (no worker graph to run)")
    with _client("tenant-a", graph=GRAPH) as a:
        try:
            r = a.post("/threads", json={"metadata": {"s01": uuid.uuid4().hex[:8]}})
        except httpx.ConnectError as exc:
            pytest.skip(f"Aegra not reachable: {exc}")
        assert r.status_code == 200, r.text
        tid = r.json()["thread_id"]
        r = a.post(f"/threads/{tid}/runs", json={"assistant_id": GRAPH,
                                                 "input": {"messages": [{"role": "human", "content": "Say ok"}]}})
        assert r.status_code == 200, r.text
        rid = r.json()["run_id"]
        j = a.get(f"/threads/{tid}/runs/{rid}/join", timeout=300.0)  # wait so B probes a finished run too
        assert j.status_code == 200, j.text
    return tid, rid


def test_s01_tenant_a_reads_its_own_thread_and_run(a_run):
    tid, rid = a_run
    with _client("tenant-a", graph=GRAPH) as a:
        assert a.get(f"/threads/{tid}").status_code == 200
        assert a.get(f"/threads/{tid}/runs/{rid}").status_code == 200
        assert rid in {r["run_id"] for r in a.get(f"/threads/{tid}/runs").json()}


@pytest.mark.parametrize("method,path", [
    ("GET", "/threads/{tid}"),
    ("GET", "/threads/{tid}/state"),
    ("GET", "/threads/{tid}/history"),
    ("GET", "/threads/{tid}/runs/{rid}"),
    ("GET", "/threads/{tid}/runs/{rid}/join"),
    ("GET", "/threads/{tid}/runs/{rid}/stream"),
    ("GET", "/threads/{tid}/runs"),
])
def test_s01_tenant_b_cannot_reach_a_thread_or_run(a_run, method, path):
    tid, rid = a_run
    with _client("tenant-b", graph=GRAPH) as b:
        r = b.request(method, path.format(tid=tid, rid=rid))
    if path.endswith("/runs") and r.status_code == 200:
        assert r.json() == [], f"B lists A's runs: {r.text[:200]}"
        return
    assert r.status_code in DENIED, f"{method} {path}: {r.status_code} {r.text[:200]}"
    assert "Say ok" not in r.text and "tenant-a" not in r.text  # the 404 may echo the id B sent, nothing of A


def test_s01_tenant_b_cannot_run_on_a_thread(a_run):
    tid, _ = a_run
    with _client("tenant-b", graph=GRAPH) as b:
        r = b.post(f"/threads/{tid}/runs", json={"assistant_id": GRAPH,
                                                 "input": {"messages": [{"role": "human", "content": "leak"}]}})
    assert r.status_code in DENIED, r.text[:200]


def test_s01_tenant_b_search_does_not_list_a_thread(a_run):
    tid, _ = a_run
    with _client("tenant-b", graph=GRAPH) as b:
        r = b.post("/threads/search", json={"limit": 100})
    assert r.status_code == 200, r.text
    assert tid not in {t["thread_id"] for t in r.json()}
