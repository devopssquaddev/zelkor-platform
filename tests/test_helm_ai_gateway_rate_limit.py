"""Helm render of CE AI Gateway global /v1 RPM (no cluster)."""
from __future__ import annotations

from tests.test_helm_ai_gateway_providers import _docs, _helm, _kinds, _named

PROVIDER = (
    "--set",
    "workspace.models.providers.openai.apiKey=sk-test",
)


def _rate_btps(docs: list[dict]) -> list[dict]:
    return [
        d
        for d in _kinds(docs, "BackendTrafficPolicy")
        if d.get("metadata", {}).get("name") == "zelkor-platform-aigateway-ratelimit"
    ]


def test_default_global_rpm_50_on_aigateway_httproute():
    docs = _docs(_helm(*PROVIDER))
    btp = _named(docs, "BackendTrafficPolicy", "zelkor-platform-aigateway-ratelimit")
    dumped = str(btp)
    assert "Burst_Test" not in dumped
    assert "Rate_Test" not in dumped
    refs = btp["spec"]["targetRefs"]
    assert len(refs) == 1
    assert refs[0]["kind"] == "HTTPRoute"
    # NeMo intercept (default): only NeMo -> provider calls are counted, all on the NeMo route.
    assert refs[0]["name"] == "zelkor-platform-aigateway-nemo-route"
    assert refs[0]["name"] != "zelkor-platform-aegra-route"
    assert btp["spec"]["mergeType"] == "StrategicMerge"
    rl = btp["spec"]["rateLimit"]
    assert rl["type"] == "Global"
    rules = rl["global"]["rules"]
    assert len(rules) == 1
    rule = rules[0]
    assert rule["limit"]["requests"] == 50
    assert rule["limit"]["unit"] == "Minute"
    labels = btp["metadata"].get("labels") or {}
    assert labels.get("zelkor.io/intent") == "workspace.models.rateLimit"


def test_overlay_requests_per_minute_10():
    docs = _docs(_helm(*PROVIDER, "--set", "workspace.models.rateLimit.requestsPerMinute=10"))
    btp = _named(docs, "BackendTrafficPolicy", "zelkor-platform-aigateway-ratelimit")
    assert btp["spec"]["rateLimit"]["global"]["rules"][0]["limit"]["requests"] == 10


def test_rate_limit_disabled_omits_btp():
    docs = _docs(_helm(*PROVIDER, "--set", "workspace.models.rateLimit.enabled=false"))
    assert _rate_btps(docs) == []


def test_no_providers_omits_rate_limit_btp():
    docs = _docs(_helm())
    assert _rate_btps(docs) == []


BYPASS = {"name": "x-zelkor-guardrails-bypass", "type": "Exact", "value": "1"}


def _rule(*extra: str) -> dict:
    docs = _docs(_helm(*PROVIDER, *extra))
    btp = _named(docs, "BackendTrafficPolicy", "zelkor-platform-aigateway-ratelimit")
    return btp["spec"]["rateLimit"]["global"]["rules"][0]


def test_bug02_one_shared_counter_across_route_rules():
    """BUG-02: one install-wide bucket, not one counter per aigateway-route rule."""
    assert _rule()["shared"] is True
    assert _rule("--set", "workspace.policies.nemo.intercept.enabled=false")["shared"] is True
    two_providers = ("--set", "workspace.models.providers.anthropic.apiKey=sk-ant-test")
    assert _rule(*two_providers)["shared"] is True


def test_bug02_intercept_counts_only_the_provider_hop():
    """NeMo intercept: agent -> NeMo is uncounted; NeMo -> provider carries the bypass header."""
    selectors = _rule()["clientSelectors"]
    assert selectors == [{"headers": [BYPASS]}]


def test_bug02_without_intercept_every_v1_call_counts():
    rule = _rule("--set", "workspace.policies.nemo.intercept.enabled=false")
    assert "clientSelectors" not in rule
    rule = _rule("--set", "workspace.policies.nemo.enabled=false")
    assert "clientSelectors" not in rule


def test_bug02_unknown_model_reject_route_not_targeted():
    docs = _docs(_helm(*PROVIDER))
    btp = _named(docs, "BackendTrafficPolicy", "zelkor-platform-aigateway-ratelimit")
    names = [r["name"] for r in btp["spec"]["targetRefs"]]
    assert names == ["zelkor-platform-aigateway-nemo-route"]
    off = _docs(_helm(*PROVIDER, "--set", "workspace.policies.nemo.intercept.enabled=false"))
    off_btp = _named(off, "BackendTrafficPolicy", "zelkor-platform-aigateway-ratelimit")
    assert [r["name"] for r in off_btp["spec"]["targetRefs"]] == ["zelkor-platform-aigateway-route"]
