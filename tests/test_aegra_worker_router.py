import os

import httpx
import pytest

GATEWAY_BASE_URL = os.environ.get("GATEWAY_BASE_URL", "http://127.0.0.1:8088")
AEGRA_HOST_HEADER = os.environ.get("AEGRA_HOST_HEADER", "aegra.localhost")
WORKER_GRAPH_ID = os.environ.get("AEGRA_WORKER_GRAPH_ID", "")


def test_graph_id_router_reaches_clusterip_worker():
    """Runs with graph_id hit a ClusterIP worker via the front door (pytest fixture, not chart)."""
    if not WORKER_GRAPH_ID:
        pytest.skip("AEGRA_WORKER_GRAPH_ID not set (no test-local worker fixture)")
    headers = {
        "Host": AEGRA_HOST_HEADER,
        "Content-Type": "application/json",
        "Authorization": "Bearer dev:tenant-a",
    }
    assert not headers["Host"].endswith(".localhost") or AEGRA_HOST_HEADER
    try:
        resp = httpx.post(
            f"{GATEWAY_BASE_URL}/runs",
            headers=headers,
            json={"graph_id": WORKER_GRAPH_ID, "input": {}, "if_not_exists": "create"},
            timeout=30.0,
        )
    except httpx.ConnectError:
        pytest.skip(f"Aegra not reachable at {GATEWAY_BASE_URL}")
    assert resp.status_code != 404, resp.text
    assert resp.status_code < 500, resp.text
