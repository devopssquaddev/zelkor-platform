"""CE-15a-4: secretless HTTP APIs (workspace.tools.httpApis) — gateway credential injection +
method/path policy. Render-only; the live half is in internal/plan/requirements_perimeter_profile.md."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tests.test_helm_values_schema import _docs, _helm

GITHUB = {
    "name": "github",
    "url": "https://api.github.com",
    "credential": {"secretRef": "github-api"},
    "rules": [
        {"action": "Deny", "methods": ["DELETE"]},
        {"action": "Allow", "methods": ["GET", "HEAD"], "path": "/repos/"},
        {"action": "Allow", "path": {"type": "RegularExpression", "value": "^/orgs/[^/]+/issues$"}},
        {"action": "Allow", "methods": ["POST"], "path": {"type": "Exact", "value": "/graphql"}},
    ],
}


def _render(tmp_path: Path, apis: list, *extra: str):
    vf = tmp_path / "apis.yaml"
    vf.write_text(yaml.safe_dump({"workspace": {"tools": {"httpApis": apis}}}))
    return _helm(*extra, values_files=[vf])


def _api_docs(tmp_path: Path, apis: list, *extra: str) -> list[dict]:
    r = _render(tmp_path, apis, *extra)
    assert r.returncode == 0, r.stderr
    return [d for d in _docs(r.stdout) if d
            and d.get("metadata", {}).get("labels", {}).get("app.kubernetes.io/component") == "http-api"]


def _one(docs: list[dict], kind: str, name: str) -> dict:
    hits = [d for d in docs if d["kind"] == kind and d["metadata"]["name"] == name]
    assert len(hits) == 1, f"{kind}/{name}: {[(d['kind'], d['metadata']['name']) for d in docs]}"
    return hits[0]


def test_no_http_apis_renders_nothing(tmp_path):
    assert _api_docs(tmp_path, []) == []


def test_http_api_relay_objects(tmp_path):
    docs = _api_docs(tmp_path, [GITHUB])
    svc = _one(docs, "Service", "zelkor-platform-api-github")
    assert svc["spec"]["type"] == "ExternalName"

    backend = _one(docs, "Backend", "zelkor-platform-api-github")
    assert backend["spec"]["endpoints"] == [{"fqdn": {"hostname": "api.github.com", "port": 443}}]
    tls = _one(docs, "BackendTLSPolicy", "zelkor-platform-api-github-tls")
    assert tls["spec"]["validation"]["hostname"] == "api.github.com"

    filt = _one(docs, "HTTPRouteFilter", "zelkor-platform-api-github-credential")
    ci = filt["spec"]["credentialInjection"]
    assert ci["credential"]["valueRef"] == {"group": "", "kind": "Secret", "name": "github-api"}
    assert ci["header"] == "Authorization"
    assert ci["overwrite"] is True

    route = _one(docs, "HTTPRoute", "zelkor-platform-api-github")
    assert route["spec"]["hostnames"] == ["zelkor-platform-api-github",
                                         "zelkor-platform-api-github.zelkor.svc.cluster.local"]
    rule = route["spec"]["rules"][0]
    assert rule["matches"] == [{"path": {"type": "PathPrefix", "value": "/"}}]
    # the upstream sees its own host (virtual-hosted APIs reject the relay's hostname)
    assert {"type": "URLRewrite", "urlRewrite": {"hostname": "api.github.com"}} in rule["filters"]
    assert {"type": "ExtensionRef", "extensionRef": {
        "group": "gateway.envoyproxy.io", "kind": "HTTPRouteFilter",
        "name": "zelkor-platform-api-github-credential"}} in rule["filters"]
    assert rule["backendRefs"] == [{"group": "gateway.envoyproxy.io", "kind": "Backend",
                                    "name": "zelkor-platform-api-github", "port": 443}]


def test_http_api_policy_is_consumer_key_plus_first_match_default_deny(tmp_path):
    sp = _one(_api_docs(tmp_path, [GITHUB]), "SecurityPolicy", "zelkor-platform-api-github")
    assert sp["spec"]["targetRefs"] == [{"group": "gateway.networking.k8s.io", "kind": "HTTPRoute",
                                         "name": "zelkor-platform-api-github"}]
    auth = sp["spec"]["apiKeyAuth"]
    assert auth["credentialRefs"] == [{"name": "zelkor-platform-ai-gateway-consumer"}]
    assert auth["extractFrom"] == [{"headers": ["authorization"]}]
    assert auth["sanitize"] is True
    assert "forwardClientIDHeader" not in auth  # the caller id never reaches a third-party API
    authz = sp["spec"]["authorization"]
    assert authz["defaultAction"] == "Deny"
    assert [(r["action"], r["cel"]) for r in authz["rules"]] == [
        ("Deny", 'request.method in ["DELETE"]'),
        ("Allow", 'request.method in ["GET", "HEAD"] && request.url_path.startsWith("/repos/")'),
        ("Allow", 'request.url_path.matches("^/orgs/[^/]+/issues$")'),
        ("Allow", 'request.method in ["POST"] && request.url_path == "/graphql"'),
    ]


def test_http_api_without_credential_and_with_path_prefix(tmp_path):
    api = {"name": "billing", "url": "http://billing.internal.example:8080/api/v2",
           "rules": [{"action": "Allow"}]}
    docs = _api_docs(tmp_path, [api])
    assert not [d for d in docs if d["kind"] == "BackendTLSPolicy"
                or d["metadata"]["name"].endswith("-credential")]
    backend = _one(docs, "Backend", "zelkor-platform-api-billing")
    assert backend["spec"]["endpoints"][0]["fqdn"] == {"hostname": "billing.internal.example", "port": 8080}
    rule = _one(docs, "HTTPRoute", "zelkor-platform-api-billing")["spec"]["rules"][0]
    # Envoy Gateway trims the slash of a ReplacePrefixMatch on "/" (live: /api/v2repos/x), so the
    # prefix is a regex rewrite of the leading "/": /repos/x -> /api/v2/repos/x, / -> /api/v2/
    assert rule["filters"] == [
        {"type": "URLRewrite", "urlRewrite": {"hostname": "billing.internal.example"}},
        {"type": "ExtensionRef", "extensionRef": {"group": "gateway.envoyproxy.io", "kind": "HTTPRouteFilter",
                                                  "name": "zelkor-platform-api-billing-prefix"}}]
    prefix = _one(docs, "HTTPRouteFilter", "zelkor-platform-api-billing-prefix")
    assert prefix["spec"]["urlRewrite"] == {"path": {"type": "ReplaceRegexMatch", "replaceRegexMatch": {
        "pattern": "^/", "substitution": "/api/v2/"}}}
    rules = _one(docs, "SecurityPolicy", "zelkor-platform-api-billing")["spec"]["authorization"]["rules"]
    assert rules == [{"name": "billing-0", "action": "Allow", "cel": "true"}]


def test_http_api_custom_header(tmp_path):
    api = dict(GITHUB, credential={"secretRef": "stripe", "header": "X-Api-Key"})
    filt = _one(_api_docs(tmp_path, [api]), "HTTPRouteFilter", "zelkor-platform-api-github-credential")
    assert filt["spec"]["credentialInjection"]["header"] == "X-Api-Key"


def test_http_apis_published_in_contract(tmp_path):
    r = _render(tmp_path, [GITHUB, dict(GITHUB, name="gh-enterprise")])
    assert r.returncode == 0, r.stderr
    cm = [d for d in _docs(r.stdout) if d and d["kind"] == "ConfigMap"
          and d["metadata"]["name"] == "zelkor-platform-contract"][0]
    assert cm["data"]["HTTP_APIS"] == "github,gh-enterprise"


def test_contract_has_no_http_apis_key_by_default(tmp_path):
    r = _render(tmp_path, [])
    cm = [d for d in _docs(r.stdout) if d and d["kind"] == "ConfigMap"
          and d["metadata"]["name"] == "zelkor-platform-contract"][0]
    assert "HTTP_APIS" not in cm["data"]


def test_http_api_relay_does_not_share_ai_gateway_host(tmp_path):
    r = _render(tmp_path, [GITHUB])
    docs = _docs(r.stdout)
    ai = [d for d in docs if d and d["kind"] == "AIGatewayRoute"]
    api = _one([d for d in docs if d], "HTTPRoute", "zelkor-platform-api-github")
    for route in ai:
        assert set(route["spec"].get("hostnames") or []).isdisjoint(api["spec"]["hostnames"])


@pytest.mark.parametrize("api,needle", [
    ({"url": "https://x.example", "rules": [{"action": "Allow"}]}, "httpApis[0].name is required"),
    (dict(GITHUB, name="Bad_Name"), "must be a DNS label"),
    (dict(GITHUB, url="ftp://x.example"), "url must be http(s)"),
    (dict(GITHUB, url="https://"), "url must be http(s)"),
    (dict(GITHUB, rules=[]), "at least one Allow rule"),
    (dict(GITHUB, rules=[{"action": "Deny"}]), "at least one Allow rule"),
    (dict(GITHUB, rules=[{"action": "Maybe"}]), "action must be Allow or Deny"),
    (dict(GITHUB, rules=[{"action": "Allow", "methods": ["get"]}]), "unknown method"),
    (dict(GITHUB, rules=[{"action": "Allow", "path": "repos"}]), "must start with /"),
    (dict(GITHUB, rules=[{"action": "Allow", "path": {"type": "Glob", "value": "/x"}}]),
     "path.type must be"),
    (dict(GITHUB, credential={"header": "X-Key"}), "credential.secretRef is required"),
    (dict(GITHUB, extra=True), "extra"),
])
def test_invalid_http_api_fails_render(tmp_path, api, needle):
    r = _render(tmp_path, [api])
    assert r.returncode != 0
    assert needle in r.stderr, r.stderr


def test_duplicate_http_api_names_fail(tmp_path):
    r = _render(tmp_path, [GITHUB, GITHUB])
    assert r.returncode != 0
    assert 'duplicate name "github"' in r.stderr


def test_http_apis_need_the_ai_gateway(tmp_path):
    r = _render(tmp_path, [GITHUB], "--set", "workspace.models.enabled=false")
    assert r.returncode != 0
    assert "workspace.tools.httpApis needs the AI gateway" in r.stderr
