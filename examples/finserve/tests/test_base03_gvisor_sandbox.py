from finserve_e2e import GRAPH_CODER, GRAPH_QUANT, run_finserve


def test_base03_agent_code_execution_smoke():
    """E2E smoke: quant graph routes a code execution request through MCP sandbox tooling."""
    result = run_finserve(
        "Use the sandbox tool to execute this Python and return the output:\n"
        "```python\nprint('sandbox-ok')\n```",
        timeout=120.0,
        graph_id=GRAPH_QUANT,
    )
    text = result["text"].lower()
    assert result["text"]
    assert "sandbox" in text or "ok" in text or "print" in text


def test_base03_coder_portfolio_python_smoke():
    """E2E smoke: Deep Agent fetches holdings then runs Python via execute()."""
    result = run_finserve(
        "Query my portfolios, then use execute() (not sandbox__execute_python) to run "
        "Python that prints TOTAL=<sum of balances>. Reply with that TOTAL line.",
        timeout=180.0,
        graph_id=GRAPH_CODER,
    )
    assert result["text"]
