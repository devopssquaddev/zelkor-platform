import os
import pytest
import httpx
import uuid

GATEWAY_BASE_URL = os.environ.get("GATEWAY_BASE_URL", "http://127.0.0.1:8088")


def test_aegra_runtime_health():
    """Platform Aegra serves Agent Protocol with no default graphs."""
    headers = {"Host": "aegra.localhost"}
    try:
        resp = httpx.get(f"{GATEWAY_BASE_URL}/health", headers=headers, timeout=5.0)
        assert resp.status_code == 200, f"Aegra /health failed: {resp.text}"
    except httpx.ConnectError:
        pytest.skip(f"Aegra gateway endpoint not reachable at {GATEWAY_BASE_URL}")


def test_aegra_thread_create_without_graph():
    """Threads persist via Aegra's checkpointer; the platform chart ships no graph."""
    thread_id = f"test-thread-{uuid.uuid4().hex[:8]}"
    headers = {
        "Host": "aegra.localhost",
        "Content-Type": "application/json",
        "Authorization": "Bearer dev:tenant_a",
    }
    try:
        create = httpx.post(
            f"{GATEWAY_BASE_URL}/threads",
            headers=headers,
            json={"thread_id": thread_id, "if_exists": "do_nothing"},
            timeout=10.0,
        )
        assert create.status_code == 200, f"Failed to create thread: {create.text}"
        body = create.json()
        assert body.get("thread_id") == thread_id

        state = httpx.get(
            f"{GATEWAY_BASE_URL}/threads/{thread_id}/state",
            headers=headers,
            timeout=10.0,
        )
        assert state.status_code == 200, f"Failed to fetch state: {state.text}"
        assert "values" in state.json()
    except httpx.ConnectError:
        pytest.skip(f"Aegra gateway endpoint not reachable at {GATEWAY_BASE_URL}")
