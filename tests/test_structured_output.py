"""NeMo must return parseable JSON for Langfuse's default eval-model probe."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

from pydantic import BaseModel

_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_root / "images" / "guardrails"))

from structured_output import (  # noqa: E402
    _CaptureResponseFormat,
    attach_response_format,
    current_response_format,
    ensure_response_format_field,
    install,
    json_object_payload,
    rewrite_completion,
)


def test_json_object_payload_strips_think_prefix():
    raw = '<think>score is five</think>\n{"score":"5","reasoning":"matched"}'
    assert json.loads(json_object_payload(raw)) == {"score": "5", "reasoning": "matched"}


def test_json_object_payload_strips_fence_and_prose():
    raw = 'Here is the object:\n```json\n{"score": "4", "reasoning": "ok"}\n```'
    assert json.loads(json_object_payload(raw))["score"] == "4"


def test_json_object_payload_leaves_prose():
    assert json_object_payload("This is a test. It worked perfectly.") is None


def test_attach_response_format_copies_schema_onto_llm_params():
    body = SimpleNamespace(
        response_format={"type": "json_schema", "json_schema": {"name": "score"}},
        guardrails=SimpleNamespace(options=SimpleNamespace(llm_params=None)),
    )
    attach_response_format(body)
    assert body.guardrails.options.llm_params["response_format"]["type"] == "json_schema"


def test_attach_ignores_unstructured_calls():
    body = SimpleNamespace(
        response_format=None,
        guardrails=SimpleNamespace(options=SimpleNamespace(llm_params={"temperature": 0})),
    )
    attach_response_format(body)
    assert "response_format" not in body.guardrails.options.llm_params


def test_rewrite_completion_replaces_think_prefixed_json():
    message = SimpleNamespace(content='<think>x</think>{"score":"5","reasoning":"ok"}')
    result = SimpleNamespace(choices=[SimpleNamespace(message=message)])
    rewrite_completion(result, {"type": "json_object"})
    assert json.loads(message.content) == {"score": "5", "reasoning": "ok"}


def test_ensure_response_format_field_accepts_schema():
    class Request(BaseModel):
        model: str

    ensure_response_format_field(Request)
    parsed = Request.model_validate(
        {"model": "gpt-oss:20b", "response_format": {"type": "json_schema", "json_schema": {}}}
    )
    assert parsed.response_format["type"] == "json_schema"


def test_middleware_restores_dropped_response_format():
    seen = {}

    async def app(scope, receive, send):
        message = await receive()
        seen["body"] = json.loads(message["body"])
        seen["format"] = current_response_format()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def receive():
        return {
            "type": "http.request",
            "body": b'{"model":"gpt-oss:20b","response_format":{"type":"json_object"}}',
            "more_body": False,
        }

    sent = []

    async def send(message):
        sent.append(message["type"])

    import asyncio

    asyncio.run(
        _CaptureResponseFormat(app)(
            {"type": "http", "path": "/v1/chat/completions"},
            receive,
            send,
        )
    )
    assert seen["format"]["type"] == "json_object"
    assert seen["body"]["model"] == "gpt-oss:20b"


def test_install_replaces_chat_completions_endpoint():
    class Request(BaseModel):
        model: str

    class Schema:
        OpenAIChatCompletionRequest = Request
        GuardrailsChatCompletionRequest = Request

    calls = {}

    async def original(body, request):
        calls["params"] = body.guardrails.options.llm_params
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='<think>n</think>{"score":"1","reasoning":"r"}'))]
        )

    dependant = SimpleNamespace(call=original)
    route = SimpleNamespace(path="/v1/chat/completions", methods={"POST"}, endpoint=original, dependant=dependant)

    class Api:
        chat_completion = staticmethod(original)
        app = SimpleNamespace(routes=[route])

    # staticmethod unwraps; install expects a callable attribute
    Api.chat_completion = original
    assert install(Api, Schema) is True

    body = SimpleNamespace(
        response_format={"type": "json_schema", "json_schema": {"name": "score"}},
        guardrails=SimpleNamespace(options=SimpleNamespace(llm_params=None)),
    )
    import asyncio

    result = asyncio.run(route.dependant.call(body, None))
    assert calls["params"]["response_format"]["type"] == "json_schema"
    assert json.loads(result.choices[0].message.content)["score"] == "1"
    assert install(Api, Schema) is True
