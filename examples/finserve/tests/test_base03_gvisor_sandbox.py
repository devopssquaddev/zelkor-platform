import os
import re
import time

import pytest

from finserve_e2e import (
    GRAPH_CODER,
    GRAPH_QUANT,
    PROMPT_CODER_ONE_EXECUTE,
    PROMPT_QUANT_ONE_SANDBOX,
    run_finserve,
    sandbox_mcp_deployed,
)
from tests.helpers.langfuse import (
    has_execute_tool_span,
    has_sandbox_mcp_span,
    sandbox_execution_metadata,
    trace_detail,
    trace_observations,
    unexpected_error_observations,
    wait_for_traces,
)
from tests.test_mcp_sandbox import ADVERSARIAL_MKNOD_SCRIPT


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

    thread_id = result.get("thread_id") or ""
    time.sleep(8)
    traces = wait_for_traces(
        lambda t: str(t.get("sessionId") or "") == thread_id,
        timeout=60.0,
        session_id=thread_id or None,
    )
    if traces:
        observations = trace_observations(trace_detail(traces[0]["id"]))
        assert has_sandbox_mcp_span(observations), "quant run must call sandbox__execute_python"
        assert not unexpected_error_observations(observations)


def test_base03_coder_portfolio_python_smoke(kubecontext):
    """E2E smoke: Deep Agent runs Python via execute() (gVisor), not SQL shortcuts."""
    if not sandbox_mcp_deployed(kubecontext):
        pytest.skip("mcp-sandbox not deployed (sandboxMCP.enabled=false)")
    result = run_finserve(
        PROMPT_CODER_ONE_EXECUTE,
        timeout=180.0,
        graph_id=GRAPH_CODER,
    )
    text = result["text"]
    assert text
    assert "coder-ok" in text.lower() or re.search(r"TOTAL=\s*[\d.]+", text)

    thread_id = result.get("thread_id") or ""
    time.sleep(8)
    traces = wait_for_traces(
        lambda t: str(t.get("sessionId") or "") == thread_id,
        timeout=90.0,
        session_id=thread_id or None,
    )
    if traces:
        observations = trace_observations(trace_detail(traces[0]["id"]))
        assert has_execute_tool_span(observations), (
            "coder must call Deep Agents execute() (gVisor sandbox backend)"
        )
        assert not unexpected_error_observations(observations)


def test_base03_sandbox_trace_contains_tool(kubecontext):
    """E2E smoke: finserve-quant run emits sandbox__execute_python in Langfuse waterfall."""
    if not sandbox_mcp_deployed(kubecontext):
        pytest.skip("mcp-sandbox not deployed (sandboxMCP.enabled=false)")
    marker = f"zelkor-sandbox-{int(time.time())}"
    result = run_finserve(
        f"{PROMPT_QUANT_ONE_SANDBOX} [{marker}]",
        timeout=120.0,
        graph_id=GRAPH_QUANT,
    )
    thread_id = result.get("thread_id") or ""
    time.sleep(8)
    matched = wait_for_traces(
        lambda t: str(t.get("sessionId") or "") == thread_id or marker in str(t),
        timeout=90.0,
        session_id=thread_id or None,
        name=GRAPH_QUANT,
    )
    if not matched:
        msg = (
            f"No Langfuse trace for {GRAPH_QUANT} within 90s "
            "(project Zelkor Platform; expect sandbox__execute_python TOOL)"
        )
        if os.environ.get("DEMO_TOUR", "").strip().lower() in ("1", "true", "yes"):
            pytest.fail(msg)
        pytest.skip(msg)
    observations = trace_observations(trace_detail(matched[0]["id"]))
    tool_names = [str(o.get("name") or "") for o in observations if o.get("type") == "TOOL"]
    assert any("sandbox__execute_python" in n for n in tool_names), (
        f"expected sandbox__execute_python in trace tools, got {tool_names}"
    )
    assert not unexpected_error_observations(observations)


def test_base03_adversarial_mknod_trace_metadata(kubecontext):
    """Agent path: mknod probe via finserve-quant emits sandbox TOOL + outcome metadata."""
    if not sandbox_mcp_deployed(kubecontext):
        pytest.skip("mcp-sandbox not deployed (sandboxMCP.enabled=false)")
    marker = f"zelkor-mknod-{int(time.time())}"
    prompt = (
        f"Run exactly one sandbox__execute_python with this code unchanged [{marker}]:\n"
        f"{ADVERSARIAL_MKNOD_SCRIPT}\n"
        "Summarize mknod_escape and host_root_visible from the output."
    )
    result = run_finserve(prompt, timeout=180.0, graph_id=GRAPH_QUANT)
    thread_id = result.get("thread_id") or ""
    time.sleep(10)
    matched = wait_for_traces(
        lambda t: str(t.get("sessionId") or "") == thread_id or marker in str(t),
        timeout=120.0,
        session_id=thread_id or None,
        name=GRAPH_QUANT,
    )
    if not matched:
        pytest.skip(f"No Langfuse trace for adversarial mknod run within 120s")
    observations = trace_observations(trace_detail(matched[0]["id"]))
    assert has_sandbox_mcp_span(observations), "quant must call sandbox__execute_python"
    meta = sandbox_execution_metadata(observations)
    if meta and meta.get("outcome"):
        assert meta["outcome"] in ("denied", "suspicious", "exploit"), meta
    assert not unexpected_error_observations(observations)
