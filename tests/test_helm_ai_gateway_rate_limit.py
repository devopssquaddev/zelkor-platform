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
    assert refs[0]["name"] == "zelkor-platform-aigateway-route"
    assert refs[0]["name"] != "zelkor-platform-aegra-route"
    assert btp["spec"]["mergeType"] == "StrategicMerge"
    rl = btp["spec"]["rateLimit"]
    assert rl["type"] == "Global"
    rule = rl["global"]["rules"][0]
    assert "clientSelectors" not in rule
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
