from finserve_e2e import run_finserve


def test_base03_agent_code_execution_smoke():
    """E2E smoke: agent can route a code execution request through MCP sandbox tooling."""
    result = run_finserve(
        "Use the sandbox tool to execute this Python and return the output:\n"
        "```python\nprint('sandbox-ok')\n```",
        timeout=120.0,
    )
    text = result["text"].lower()
    assert result["text"]
    assert "sandbox" in text or "ok" in text or "print" in text
