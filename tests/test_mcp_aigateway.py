import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mcp"))

from tests.helpers.llm import llm_model_or_skip
from tests.helpers.mcp_client import MCPGatewayClient
from wrappers.aigateway_server import (
    AIGatewayMCPServer,
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


def test_call_rejects_disallowed_model():
    server = AIGatewayMCPServer(allowed_models=["allowed/model"])
    with pytest.raises(PermissionError, match="not allowed"):
        server.call_tool(
            "call",
            {
                "model": "other/model",
                "messages": [{"role": "user", "content": "hi"}],
            },
            "tenant_a",
        )


def test_post_gateway_uses_consumer_key_only(monkeypatch):
    monkeypatch.setattr("wrappers.aigateway_server.AI_GATEWAY_URL", "http://ai-gateway:80/v1")
    monkeypatch.setattr("wrappers.aigateway_server.AI_GATEWAY_API_KEY", "cluster-consumer")
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


def test_mcp_aigateway_rejects_url_arg():
    client = MCPGatewayClient("tenant_a")
    try:
        with pytest.raises(RuntimeError, match="(?i)url|reject"):
            client.call_tool(
                "aigateway__call",
                {
                    "model": "openai/gpt-4o-mini",
                    "url": "https://evil.example/v1",
                    "messages": [{"role": "user", "content": "hi"}],
                },
            )
    except ConnectionError as exc:
        pytest.skip(str(exc))


def test_mcp_aigateway_rejects_stray_tenant_id():
    client = MCPGatewayClient("tenant_a")
    try:
        with pytest.raises(RuntimeError, match="(?i)tenant_id"):
            client.call_tool(
                "aigateway__call",
                {
                    "tenant_id": "tenant_b",
                    "model": "openai/gpt-4o-mini",
                    "messages": [{"role": "user", "content": "hi"}],
                },
            )
    except ConnectionError as exc:
        pytest.skip(str(exc))


def test_mcp_aigateway_chat_via_ai_gateway():
    model = llm_model_or_skip()
    client = MCPGatewayClient("tenant_a")
    try:
        result = client.call_tool(
            "aigateway__call",
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


def test_call_schema_spells_out_chat_messages_and_operations():
    """Models fill tool arguments from the schema; an untyped `messages` invited malformed calls."""
    (tool,) = AIGatewayMCPServer(allowed_models=["m"]).list_tools()
    props = tool["inputSchema"]["properties"]
    assert props["operation"]["enum"] == ["chat.completions", "embeddings"]
    item = props["messages"]["items"]
    assert item["required"] == ["role", "content"]
    assert "chat.completions" in props["messages"]["description"]
    assert "embeddings" in props["input"]["description"]


def test_gateway_call_continues_the_callers_trace(monkeypatch):
    """The tool's /v1 call joins the agent run's trace instead of starting its own."""
    from common.mcp_server import TRACE_CONTEXT
    import wrappers.aigateway_server as srv

    monkeypatch.setattr(srv, "AI_GATEWAY_URL", "http://gw/v1")
    tp = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
    sent = {}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b"{}"

    def fake_urlopen(req, timeout):
        sent.update({k.lower(): v for k, v in req.header_items()})
        return _Resp()

    monkeypatch.setattr(srv.urllib.request, "urlopen", fake_urlopen)
    token = TRACE_CONTEXT.set({"traceparent": tp})
    try:
        post_gateway("chat/completions", {"model": "m", "messages": []})
    finally:
        TRACE_CONTEXT.reset(token)
    assert sent["traceparent"] == tp
    sent.clear()
    post_gateway("chat/completions", {"model": "m", "messages": []})
    assert "traceparent" not in sent
