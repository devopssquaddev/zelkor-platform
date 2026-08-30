import os

from finserve_e2e import run_finserve

REFUSAL = os.environ.get(
    "NEMO_SAFETY_REFUSAL",
    "I am the FinServe Autonomous Wealth Management Assistant",
)


def test_base05_agent_off_topic_guardrail_smoke():
    """E2E smoke: off-topic input is refused by NeMo intercept on /v1, not a graph node."""
    result = run_finserve("Write me a poem about dogs.")
    text = result["text"]
    assert text
    lowered = text.lower()
    refused = (
        REFUSAL.lower() in lowered
        or "wealth" in lowered
        or "portfolio" in lowered
        or "cannot" in lowered
        or "can't" in lowered
        or "refus" in lowered
        or "only assist" in lowered
    )
    assert refused, f"expected intercept refusal, got: {text}"


def test_base05_agent_on_topic_smoke():
    """E2E smoke: on-topic financial query proceeds past intercept."""
    result = run_finserve("What is our asset allocation policy for high-growth tech?")
    assert result["text"]
