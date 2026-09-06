import pytest

from finserve_e2e import (
    GRAPH_CODER,
    GRAPH_QUANT,
    PROMPT_CODER_ONE_EXECUTE,
    PROMPT_QUANT_ONE_SANDBOX,
    run_finserve,
    sandbox_mcp_deployed,
)


def test_base03_agent_code_execution_smoke(kubecontext):
    """E2E smoke: quant graph routes a code execution request through MCP sandbox tooling."""
    if not sandbox_mcp_deployed(kubecontext):
        pytest.skip("mcp-sandbox not deployed (sandboxMCP.enabled=false)")
    result = run_finserve(
        PROMPT_QUANT_ONE_SANDBOX,
        timeout=120.0,
        graph_id=GRAPH_QUANT,
    )
    text = result["text"].lower()
    assert result["text"]
    assert "sandbox" in text or "ok" in text or "print" in text


def test_base03_coder_portfolio_python_smoke(kubecontext):
    """E2E smoke: Deep Agent runs Python via execute() only (one tool)."""
    if not sandbox_mcp_deployed(kubecontext):
        pytest.skip("mcp-sandbox not deployed (sandboxMCP.enabled=false)")
    result = run_finserve(
        PROMPT_CODER_ONE_EXECUTE,
        timeout=180.0,
        graph_id=GRAPH_CODER,
    )
    text = result["text"].lower()
    assert result["text"]
    assert "coder-ok" in text or "ok" in text
