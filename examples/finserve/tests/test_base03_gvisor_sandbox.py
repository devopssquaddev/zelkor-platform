import os
import pytest
import httpx

GATEWAY_BASE_URL = os.environ.get("GATEWAY_BASE_URL", "http://127.0.0.1:8088")
FINSERVE_HOST_HEADER = os.environ.get("FINSERVE_HOST_HEADER", "finserve.localhost")


def test_base03_agent_code_execution_smoke():
    """E2E smoke: agent can route a code execution request through MCP sandbox tooling."""
    url = f"{GATEWAY_BASE_URL}/runs/stream"
    headers = {
        "Host": FINSERVE_HOST_HEADER,
        "Content-Type": "application/json",
        "Authorization": "Bearer dev:Bank_Alpha",
    }
    payload = {
        "assistant_id": "finserve_agent",
        "input": {
            "messages": [{
                "role": "user",
                "content": (
                    "Use the sandbox tool to execute this Python and return the output:\n"
                    "```python\nprint('sandbox-ok')\n```"
                ),
            }]
        },
    }
    try:
        resp = httpx.post(url, headers=headers, json=payload, timeout=90.0)
        assert resp.status_code == 200, f"Failed sandbox smoke call: {resp.text}"
        data = resp.json()
        assert data.get("tenant_id") == "Bank_Alpha"
        resp_data = data.get("data", {})
        assert resp_data.get("response")
        tool_results = resp_data.get("tool_results") or []
        execution = resp_data.get("execution_result")
        assert tool_results or execution or "sandbox" in resp_data.get("response", "").lower()
    except httpx.ConnectError:
        pytest.skip(f"Gateway not reachable at {GATEWAY_BASE_URL}")
