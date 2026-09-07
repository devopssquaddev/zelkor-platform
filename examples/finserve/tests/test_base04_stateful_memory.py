from finserve_e2e import GRAPH_RESEARCH, PROMPT_RESEARCH_ONE_SEARCH, run_finserve


def test_base04_stateful_thread_memory():
    """E2E smoke: two sequential research runs succeed (checkpointer / front door)."""
    first = run_finserve(PROMPT_RESEARCH_ONE_SEARCH, graph_id=GRAPH_RESEARCH)
    assert first["text"]
    second = run_finserve(PROMPT_RESEARCH_ONE_SEARCH, graph_id=GRAPH_RESEARCH)
    assert second["text"]
