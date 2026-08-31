from finserve_e2e import GRAPH_RESEARCH, run_finserve


def test_base04_stateful_thread_memory():
    """E2E smoke: two sequential research runs succeed (checkpointer / front door)."""
    first = run_finserve(
        "What is our asset allocation policy for high-growth tech?",
        graph_id=GRAPH_RESEARCH,
    )
    assert first["text"]
    second = run_finserve(
        "Summarize the risk disclosure for that allocation.",
        graph_id=GRAPH_RESEARCH,
    )
    assert second["text"]


def test_base04_policy_query_smoke():
    """E2E smoke: on-topic policy query returns an agent reply."""
    result = run_finserve(
        "What is our asset allocation policy for high-growth tech?",
        graph_id=GRAPH_RESEARCH,
    )
    assert result["text"]
