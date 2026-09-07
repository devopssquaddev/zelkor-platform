from finserve_e2e import GRAPH_ADVISOR, PROMPT_ADVISOR_ONE_QUERY, PROMPT_IDOR_ONE_QUERY, run_finserve


def test_base02_tenant_isolation_idor_smoke():
    """E2E smoke: IDOR prompt does not return Bank_Beta portfolio records."""
    result = run_finserve(PROMPT_IDOR_ONE_QUERY, graph_id=GRAPH_ADVISOR)
    text = result["text"]
    assert "ACC-BETA" not in text
    assert "Charlie Brown" not in text
    assert "Diana Prince" not in text


def test_base02_tenant_isolation_authorized_access():
    """E2E smoke: Bank_Alpha user receives a non-empty own-tenant reply."""
    result = run_finserve(PROMPT_ADVISOR_ONE_QUERY, graph_id=GRAPH_ADVISOR)
    assert result["text"]
