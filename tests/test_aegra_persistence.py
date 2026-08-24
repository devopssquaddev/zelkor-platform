import os
import pytest
import subprocess
import json
import httpx
import uuid
import time

GATEWAY_BASE_URL = os.environ.get("GATEWAY_BASE_URL", "http://127.0.0.1:8088")

def test_aegra_thread_persistence():
    """
    Verify Aegra state persistence across runs in PostgreSQL & Valkey.
    Creates a thread run, queries state, and confirms thread history is persisted.
    """
    thread_id = f"test-thread-{uuid.uuid4().hex[:8]}"
    headers = {
        "Host": "aegra.localhost",
        "Content-Type": "application/json",
        "Authorization": "Bearer dev:Bank_Alpha"
    }

    try:
        # Step 1: Create a run on new thread
        run_url = f"{GATEWAY_BASE_URL}/threads/{thread_id}/runs"
        payload = {"input": {"message": "Initial conversation turn", "account_balance": 10000}}
        resp = httpx.post(run_url, headers=headers, json=payload, timeout=5.0)
        assert resp.status_code == 200, f"Failed to create thread run: {resp.text}"
        run_data = resp.json()
        assert run_data.get("thread_id") == thread_id
        assert run_data.get("tenant_id") == "Bank_Alpha"

        # Step 2: Fetch thread state
        state_url = f"{GATEWAY_BASE_URL}/threads/{thread_id}/state"
        state_resp = httpx.get(state_url, headers=headers, timeout=5.0)
        assert state_resp.status_code == 200, f"Failed to fetch state: {state_resp.text}"
        state_data = state_resp.json()
        assert state_data.get("thread_id") == thread_id
        assert state_data.get("tenant_id") == "Bank_Alpha"
        assert len(state_data.get("history", [])) >= 1
    except httpx.ConnectError:
        pytest.skip(f"Aegra gateway endpoint not reachable at {GATEWAY_BASE_URL}")
