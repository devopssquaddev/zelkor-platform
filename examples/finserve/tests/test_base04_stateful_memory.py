from finserve_e2e import run_finserve


def test_base04_stateful_thread_memory():
    """E2E smoke: two sequential FinServe runs succeed (checkpointer / front door)."""
    first = run_finserve("Show my portfolio balance.")
    assert first["text"]
    second = run_finserve("What is our asset allocation policy for high-growth tech?")
    assert second["text"]


def test_base04_policy_query_smoke():
    """E2E smoke: on-topic policy query returns an agent reply."""
    result = run_finserve("What is our asset allocation policy for high-growth tech?")
    assert result["text"]
