import os

import httpx
import pytest

GATEWAY_BASE_URL = os.environ.get("GATEWAY_BASE_URL", "http://127.0.0.1:8088")
AEGRA_HOST_HEADER = os.environ.get("AEGRA_HOST_HEADER", "aegra.localhost")
WORKER_GRAPH_ID = os.environ.get("AEGRA_WORKER_GRAPH_ID", "")


def _headers(extra=None):
    headers = {
        "Host": AEGRA_HOST_HEADER,
        "Content-Type": "application/json",
        "Authorization": "Bearer dev:tenant-a",
    }
    if extra:
        headers.update(extra)
    return headers


def test_graph_id_header_reaches_clusterip_worker():
    """X-Graph-ID (and body graph_id) reach the owning ClusterIP worker."""
    if not WORKER_GRAPH_ID:
        pytest.skip("AEGRA_WORKER_GRAPH_ID not set (no test-local worker fixture)")
    try:
        resp = httpx.post(
            f"{GATEWAY_BASE_URL}/runs",
            headers=_headers({"X-Graph-ID": WORKER_GRAPH_ID}),
            json={"graph_id": WORKER_GRAPH_ID, "input": {}, "if_not_exists": "create"},
            timeout=30.0,
        )
    except httpx.ConnectError:
        pytest.skip(f"Aegra not reachable at {GATEWAY_BASE_URL}")
    assert resp.status_code != 404, resp.text
    assert resp.status_code != 502, resp.text
    assert resp.status_code < 500, resp.text


def test_graph_id_query_reaches_clusterip_worker():
    if not WORKER_GRAPH_ID:
        pytest.skip("AEGRA_WORKER_GRAPH_ID not set (no test-local worker fixture)")
    try:
        resp = httpx.post(
            f"{GATEWAY_BASE_URL}/runs?graph_id={WORKER_GRAPH_ID}",
            headers=_headers(),
            json={"graph_id": WORKER_GRAPH_ID, "input": {}, "if_not_exists": "create"},
            timeout=30.0,
        )
    except httpx.ConnectError:
        pytest.skip(f"Aegra not reachable at {GATEWAY_BASE_URL}")
    assert resp.status_code != 404, resp.text
    assert resp.status_code != 502, resp.text
    assert resp.status_code < 500, resp.text


def test_absent_routing_key_hits_default_not_python_502():
    """Unmatched / absent X-Graph-ID is the default backend, not a Zelkor proxy 502."""
    try:
        resp = httpx.post(
            f"{GATEWAY_BASE_URL}/runs",
            headers=_headers(),
            json={"graph_id": "missing-worker-graph", "input": {}, "if_not_exists": "create"},
            timeout=30.0,
        )
    except httpx.ConnectError:
        pytest.skip(f"Aegra not reachable at {GATEWAY_BASE_URL}")
    assert resp.status_code != 502, resp.text
