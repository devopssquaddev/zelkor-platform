import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mcp"))

from tests.helpers.mcp_client import MCPGatewayClient
from wrappers.egress_server import (
    EgressMCPServer,
    build_body,
    gateway_path,
    post_gateway,
    reject_forbidden_args,
)


def test_reject_model_supplied_url_and_auth():
    with pytest.raises(PermissionError, match="url"):
        reject_forbidden_args({"tenant_id": "t", "model": "m", "url": "https://evil.example"})
    with pytest.raises(PermissionError, match="base_url"):
        reject_forbidden_args({"base_url": "https://evil.example"})
    with pytest.raises(PermissionError, match="Authorization"):
        reject_forbidden_args({"Authorization": "Bearer stolen"})
    with pytest.raises(PermissionError, match="api_key"):
        reject_forbidden_args({"api_key": "sk-openai"})


def test_gateway_path_and_body():
    assert gateway_path("chat.completions") == "chat/completions"
    assert gateway_path("embeddings") == "embeddings"
    with pytest.raises(ValueError, match="unsupported"):
        gateway_path("images")
    body = build_body("chat.completions", {"messages": [{"role": "user", "content": "hi"}]}, "m")
    assert body == {"model": "m", "messages": [{"role": "user", "content": "hi"}]}
    emb = build_body("embeddings", {"input": "hi"}, "m")
    assert emb == {"model": "m", "input": "hi"}


def test_call_external_api_tenant_mismatch():
    server = EgressMCPServer(allowed_models=[])
    with pytest.raises(PermissionError, match="tenant_id mismatch"):
        server.call_tool(
            "call_external_api",
            {"tenant_id": "tenant_b", "model": "openai/gpt-4o-mini", "messages": []},
            "tenant_a",
        )


def test_call_external_api_rejects_disallowed_model():
    server = EgressMCPServer(allowed_models=["allowed/model"])
    with pytest.raises(PermissionError, match="not allowed"):
        server.call_tool(
            "call_external_api",
            {
                "tenant_id": "tenant_a",
                "model": "other/model",
                "messages": [{"role": "user", "content": "hi"}],
            },
            "tenant_a",
        )


def test_post_gateway_uses_consumer_key_only(monkeypatch):
    monkeypatch.setattr("wrappers.egress_server.AI_GATEWAY_URL", "http://ai-gateway:80/v1")
    monkeypatch.setattr("wrappers.egress_server.AI_GATEWAY_API_KEY", "cluster-consumer")
    captured = {}

    def fake_urlopen(req, timeout=60):
        captured["url"] = req.full_url
        captured["auth"] = req.headers.get("Authorization")
        captured["body"] = req.data
        resp = MagicMock()
        resp.read.return_value = b'{"id":"ok"}'
        resp.__enter__.return_value = resp
        resp.__exit__.return_value = False
        return resp

    with patch("urllib.request.urlopen", fake_urlopen):
        out = post_gateway("chat/completions", {"model": "m", "messages": []})
    assert out == {"id": "ok"}
    assert captured["url"] == "http://ai-gateway:80/v1/chat/completions"
    assert captured["auth"] == "Bearer cluster-consumer"
    assert b"stolen" not in (captured["body"] or b"")


def test_mcp_egress_rejects_url_arg():
    client = MCPGatewayClient("tenant_a")
    try:
        with pytest.raises(RuntimeError, match="(?i)url|reject"):
            client.call_tool(
                "egress__call_external_api",
                {
                    "model": "openai/gpt-4o-mini",
                    "url": "https://evil.example/v1",
                    "messages": [{"role": "user", "content": "hi"}],
                },
            )
    except ConnectionError as exc:
        pytest.skip(str(exc))


def test_mcp_egress_rejects_tenant_mismatch():
    client = MCPGatewayClient("tenant_a")
    try:
        with pytest.raises(RuntimeError, match="tenant_id mismatch"):
            client.call_tool(
                "egress__call_external_api",
                {
                    "tenant_id": "tenant_b",
                    "model": "openai/gpt-4o-mini",
                    "messages": [{"role": "user", "content": "hi"}],
                },
            )
    except ConnectionError as exc:
        pytest.skip(str(exc))


def test_mcp_egress_chat_via_ai_gateway():
    model = os.environ.get("DEFAULT_LLM_MODEL", "openai/gpt-4o-mini")
    client = MCPGatewayClient("tenant_a")
    try:
        result = client.call_tool(
            "egress__call_external_api",
            {
                "model": model,
                "messages": [{"role": "user", "content": "Reply with the single word pong."}],
            },
        )
    except ConnectionError as exc:
        pytest.skip(str(exc))
    except RuntimeError as exc:
        if "AI Gateway" in str(exc) or "not set" in str(exc):
            pytest.skip(str(exc))
        raise
    assert result.get("choices") or result.get("id")
