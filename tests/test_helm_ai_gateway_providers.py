"""Helm render of Envoy AI Gateway provider schemas (no cluster)."""
from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "charts" / "zelkor-platform"

SECRET_SETS = [
    "postgresql.auth.password=test-pg",
    "clickhouse.auth.password=test-ch",
    "seaweedfs.auth.accessKey=test-ak",
    "seaweedfs.auth.secretKey=test-sk",
    "langfuse.nextauthSecret=test-na",
    "langfuse.salt=test-salt-1234567890",
    "langfuse.encryptionKey=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    "langfuse.nextauthUrl=https://langfuse.example.com",
    "gateway.hosts.aiGateway=ai-gateway.example.com",
]


def _helm(*extra: str) -> str:
    cmd = ["helm", "template", "zelkor-platform", str(CHART), "--namespace", "zelkor"]
    for item in SECRET_SETS:
        cmd.extend(["--set", item])
    cmd.extend(extra)
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def _docs(rendered: str) -> list[dict]:
    return [d for d in yaml.safe_load_all(rendered) if d]


def _kinds(docs: list[dict], kind: str) -> list[dict]:
    return [d for d in docs if d.get("kind") == kind]


def _named(docs: list[dict], kind: str, name: str) -> dict:
    matches = [d for d in _kinds(docs, kind) if d["metadata"]["name"] == name]
    assert matches, f"missing {kind}/{name}"
    return matches[0]


def _route_matches(docs: list[dict]) -> list[str]:
    route = _named(docs, "AIGatewayRoute", "zelkor-platform-aigateway-route")
    values: list[str] = []
    for rule in route["spec"].get("rules") or []:
        for match in rule.get("matches") or []:
            for header in match.get("headers") or []:
                if header.get("name") == "x-ai-eg-model":
                    values.append(header.get("value") or "")
    return values


def test_empty_providers_omit_new_backends():
    docs = _docs(_helm())
    names = {d["metadata"]["name"] for d in docs if "metadata" in d}
    for suffix in (
        "backend-azure",
        "backend-bedrock",
        "backend-vertex",
        "backend-cohere",
        "backend-compat-groq",
    ):
        assert f"zelkor-platform-{suffix}" not in names


def test_gemini_openai_prefix():
    docs = _docs(_helm("--set", "aiGateway.providers.gemini.apiKey=AIza-test"))
    backend = _named(docs, "AIServiceBackend", "zelkor-platform-backend-gemini")
    assert backend["spec"]["schema"]["name"] == "OpenAI"
    assert backend["spec"]["schema"]["prefix"] == "/v1beta/openai"


def test_azure_schema_and_route():
    docs = _docs(
        _helm(
            "--set",
            "aiGateway.providers.azure.apiKey=az-key",
            "--set",
            "aiGateway.providers.azure.endpoint=https://myres.openai.azure.com",
        )
    )
    backend = _named(docs, "AIServiceBackend", "zelkor-platform-backend-azure")
    assert backend["spec"]["schema"]["name"] == "AzureOpenAI"
    host = _named(docs, "Backend", "zelkor-platform-backend-azure")
    assert host["spec"]["endpoints"][0]["fqdn"]["hostname"] == "myres.openai.azure.com"
    pol = _named(docs, "BackendSecurityPolicy", "zelkor-platform-azure-apikey")
    assert pol["spec"]["type"] == "AzureAPIKey"
    matches = _route_matches(docs)
    assert "^(azure/.*)" in matches
    assert not any("gemini-.*" in m and "azure" in m for m in matches)


def test_bedrock_and_anthropic_schema():
    docs = _docs(
        _helm(
            "--set",
            "aiGateway.providers.bedrock.accessKeyId=AKIATEST",
            "--set",
            "aiGateway.providers.bedrock.secretAccessKey=secret",
            "--set",
            "aiGateway.providers.bedrock.region=eu-west-1",
            "--set",
            "aiGateway.providers.bedrock.anthropic=true",
        )
    )
    bedrock = _named(docs, "AIServiceBackend", "zelkor-platform-backend-bedrock")
    assert bedrock["spec"]["schema"]["name"] == "AWSBedrock"
    claude = _named(docs, "AIServiceBackend", "zelkor-platform-backend-bedrock-anthropic")
    assert claude["spec"]["schema"]["name"] == "AWSAnthropic"
    host = _named(docs, "Backend", "zelkor-platform-backend-bedrock")
    assert host["spec"]["endpoints"][0]["fqdn"]["hostname"] == "bedrock-runtime.eu-west-1.amazonaws.com"
    pol = _named(docs, "BackendSecurityPolicy", "zelkor-platform-bedrock-aws")
    assert pol["spec"]["type"] == "AWSCredentials"
    matches = _route_matches(docs)
    assert "^(bedrock/.*)" in matches
    assert "^(bedrock-anthropic/.*)" in matches
    assert not any(m == "^(claude-.*)" or m.endswith("|claude-.*)") and "bedrock" in m for m in matches)


def test_vertex_and_gcp_anthropic():
    docs = _docs(
        _helm(
            "--set",
            "aiGateway.providers.vertex.project=my-proj",
            "--set",
            "aiGateway.providers.vertex.region=us-central1",
            "--set-string",
            "aiGateway.providers.vertex.credentialsJson={\"type\":\"service_account\"}",
            "--set",
            "aiGateway.providers.vertex.anthropic=true",
        )
    )
    vertex = _named(docs, "AIServiceBackend", "zelkor-platform-backend-vertex")
    assert vertex["spec"]["schema"]["name"] == "GCPVertexAI"
    claude = _named(docs, "AIServiceBackend", "zelkor-platform-backend-vertex-anthropic")
    assert claude["spec"]["schema"]["name"] == "GCPAnthropic"
    host = _named(docs, "Backend", "zelkor-platform-backend-vertex")
    assert host["spec"]["endpoints"][0]["fqdn"]["hostname"] == "us-central1-aiplatform.googleapis.com"
    pol = _named(docs, "BackendSecurityPolicy", "zelkor-platform-vertex-gcp")
    assert pol["spec"]["type"] == "GCPCredentials"
    matches = _route_matches(docs)
    assert "^(vertex/.*)" in matches
    assert "^(vertex-anthropic/.*)" in matches
    assert not any("gemini-.*" in m and "vertex" in (m or "") for m in matches)
    assert all("gemini-.*" not in m for m in matches if "vertex" in m)


def test_cohere_schema():
    docs = _docs(_helm("--set", "aiGateway.providers.cohere.apiKey=co-key"))
    backend = _named(docs, "AIServiceBackend", "zelkor-platform-backend-cohere")
    assert backend["spec"]["schema"]["name"] == "Cohere"
    matches = _route_matches(docs)
    assert "^(cohere/.*)" in matches


def test_openai_compat_item():
    docs = _docs(
        _helm(
            "--set",
            "aiGateway.providers.openaiCompat[0].name=groq",
            "--set",
            "aiGateway.providers.openaiCompat[0].host=api.groq.com",
            "--set",
            "aiGateway.providers.openaiCompat[0].prefix=/openai/v1",
            "--set",
            "aiGateway.providers.openaiCompat[0].apiKey=gsk-test",
            "--set",
            "aiGateway.providers.openaiCompat[0].modelMatch=^(groq/.*)",
        )
    )
    backend = _named(docs, "AIServiceBackend", "zelkor-platform-backend-compat-groq")
    assert backend["spec"]["schema"]["name"] == "OpenAI"
    assert backend["spec"]["schema"]["prefix"] == "/openai/v1"
    host = _named(docs, "Backend", "zelkor-platform-backend-compat-groq")
    assert host["spec"]["endpoints"][0]["fqdn"]["hostname"] == "api.groq.com"
    pol = _named(docs, "BackendSecurityPolicy", "zelkor-platform-compat-groq-apikey")
    assert pol["spec"]["type"] == "APIKey"
    assert "^(groq/.*)" in _route_matches(docs)


def _nemo_config_models(docs: list[dict]) -> list[dict]:
    cm = _named(docs, "ConfigMap", "zelkor-platform-nemo-config")
    cfg = yaml.safe_load(cm["data"]["content_safety-config.yml"])
    return cfg.get("models") or []


def _unknown_model_route(docs: list[dict]) -> dict | None:
    matches = [d for d in _kinds(docs, "HTTPRoute") if d["metadata"]["name"] == "zelkor-platform-unknown-model"]
    return matches[0] if matches else None


def _unknown_model_filter(docs: list[dict]) -> dict | None:
    matches = [d for d in _kinds(docs, "HTTPRouteFilter") if d["metadata"]["name"] == "zelkor-platform-unknown-model"]
    return matches[0] if matches else None


def _aigateway_rules(docs: list[dict]) -> list[dict]:
    return _named(docs, "AIGatewayRoute", "zelkor-platform-aigateway-route")["spec"].get("rules") or []


def test_self_check_models_inherit_nemo_model():
    docs = _docs(_helm("--set", "guardrails.nemo.model=qwen3:8b"))
    by_type = {row["type"]: row["model"] for row in _nemo_config_models(docs)}
    assert by_type["main"] == "qwen3:8b"
    assert by_type["self_check_input"] == "qwen3:8b"
    assert by_type["self_check_output"] == "qwen3:8b"


def test_self_check_model_override_does_not_change_main():
    docs = _docs(
        _helm(
            "--set",
            "guardrails.nemo.model=qwen3:8b",
            "--set",
            "guardrails.nemo.selfCheck.model=gpt-oss:20b",
        )
    )
    by_type = {row["type"]: row["model"] for row in _nemo_config_models(docs)}
    assert by_type["main"] == "qwen3:8b"
    assert by_type["self_check_input"] == "gpt-oss:20b"
    assert by_type["self_check_output"] == "gpt-oss:20b"


def test_self_check_models_omitted_when_disabled():
    docs = _docs(_helm("--set", "guardrails.nemo.selfCheck.enabled=false"))
    types = {row["type"] for row in _nemo_config_models(docs)}
    assert "main" in types
    assert "self_check_input" not in types
    assert "self_check_output" not in types


def test_unknown_bypass_reject_when_intercept_on():
    docs = _docs(_helm("--set", "aiGateway.providers.ollamaCloud.apiKey=ollama-key"))
    filt = _unknown_model_filter(docs)
    route = _unknown_model_route(docs)
    assert filt is not None
    assert filt["spec"]["directResponse"]["statusCode"] == 400
    assert "model_not_found" in filt["spec"]["directResponse"]["body"]["inline"]
    assert route is not None
    headers = route["spec"]["rules"][0]["matches"][0]["headers"]
    assert headers == [{"type": "Exact", "name": "x-zelkor-guardrails-bypass", "value": "1"}]
    assert "backendRefs" not in route["spec"]["rules"][0]
    rules = _aigateway_rules(docs)
    assert any(
        any(
            h.get("name") == "x-ai-eg-model" and "gpt-oss" in (h.get("value") or "")
            for h in (m.get("headers") or [])
        )
        for rule in rules
        for m in rule.get("matches") or []
    )
    catch = rules[-1]
    assert not catch.get("matches")
    assert catch["backendRefs"][0]["name"] == "zelkor-platform-backend-nemo"


def test_unknown_bypass_reject_absent_when_intercept_off():
    docs = _docs(
        _helm(
            "--set",
            "guardrails.nemo.intercept.enabled=false",
            "--set",
            "aiGateway.providers.ollamaCloud.apiKey=ollama-key",
        )
    )
    assert _unknown_model_route(docs) is None
    assert _unknown_model_filter(docs) is None


def test_vertex_bypass_rule_stays_two_header_when_reject_present():
    docs = _docs(
        _helm(
            "--set",
            "aiGateway.providers.vertex.project=my-proj",
            "--set",
            "aiGateway.providers.vertex.region=us-central1",
        )
    )
    assert "^(vertex/.*)" in _route_matches(docs)
    route = _unknown_model_route(docs)
    assert route is not None
    headers = route["spec"]["rules"][0]["matches"][0]["headers"]
    assert headers == [{"type": "Exact", "name": "x-zelkor-guardrails-bypass", "value": "1"}]
    vertex_rule = next(
        rule
        for rule in _aigateway_rules(docs)
        if any(
            h.get("name") == "x-ai-eg-model" and h.get("value") == "^(vertex/.*)"
            for m in rule.get("matches") or []
            for h in m.get("headers") or []
        )
    )
    names = {h.get("name") for h in vertex_rule["matches"][0]["headers"]}
    assert names == {"x-zelkor-guardrails-bypass", "x-ai-eg-model"}
