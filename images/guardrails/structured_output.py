"""Forward OpenAI structured output through NeMo and return parseable JSON.

Langfuse 4.50 ``defaultLlmModel.upsertDefaultModel`` probes the project model
with ``response_format`` json_schema (score + reasoning). NeMo's chat schema
drops that field, and reasoning models then come back with a ``<think>`` prefix
on ``content``. The AI SDK reports that as "could not parse the response."
"""
from __future__ import annotations

import json
import logging
import re
from contextvars import ContextVar
from typing import Any, Optional

_current_response_format: ContextVar[Optional[dict]] = ContextVar(
    "zelkor_response_format",
    default=None,
)

_log = logging.getLogger("zelkor-nemo")
_THINK_PREFIX = re.compile(r"^\s*<think>.*?</think>\s*", re.DOTALL)
_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)
_STRUCTURED_TYPES = frozenset({"json_schema", "json_object"})
_PATCHED = "_zelkor_structured_output"


def ensure_response_format_field(model_cls: Any) -> None:
    """Accept ``response_format`` on a NeMo request model (pydantic ignores extras)."""
    if "response_format" in getattr(model_cls, "model_fields", {}):
        return
    from pydantic.fields import FieldInfo

    model_cls.model_fields["response_format"] = FieldInfo(
        annotation=Optional[dict],
        default=None,
    )
    model_cls.model_rebuild(force=True)


def current_response_format(body: Any = None) -> Any:
    """Structured format from the parsed body, else the raw request captured by middleware."""
    response_format = getattr(body, "response_format", None) if body is not None else None
    if _is_structured(response_format):
        return response_format
    return _current_response_format.get()


def attach_response_format(body: Any) -> None:
    """Copy a structured ``response_format`` onto the LLM call params NeMo forwards."""
    response_format = current_response_format(body)
    if not _is_structured(response_format):
        return
    guardrails = getattr(body, "guardrails", None)
    options = getattr(guardrails, "options", None)
    if options is None:
        return
    params = getattr(options, "llm_params", None)
    if params is None:
        params = {}
        options.llm_params = params
    params["response_format"] = response_format


def json_object_payload(content: str) -> Optional[str]:
    """Return canonical JSON when ``content`` is an object, after think-tags or fences."""
    text = _THINK_PREFIX.sub("", content, count=1).strip()
    fenced = _FENCE.match(text)
    if fenced:
        text = fenced.group(1).strip()
    if not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return None
        text = text[start : end + 1]
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(value, dict):
        return None
    return json.dumps(value, ensure_ascii=False)


def rewrite_completion(result: Any, response_format: Any) -> Any:
    """Replace assistant content with the JSON object when a structured call asked for one."""
    if not _is_structured(response_format):
        return result
    choices = getattr(result, "choices", None) or []
    if not choices:
        return result
    message = getattr(choices[0], "message", None)
    content = getattr(message, "content", None)
    if not isinstance(content, str):
        return result
    payload = json_object_payload(content)
    if payload is None or payload == content:
        return result
    message.content = payload
    return result


def install(api_module: Any = None, schema_module: Any = None) -> bool:
    """Patch NeMo ``/v1/chat/completions`` once. Returns False if NeMo is not importable."""
    if api_module is None or schema_module is None:
        try:
            import nemoguardrails.server.api as api_module
            import nemoguardrails.server.schemas.openai as schema_module
        except Exception:
            _log.exception("structured output patch skipped; NeMo server is not importable")
            return False
    if getattr(api_module, _PATCHED, False):
        return True

    for name in ("OpenAIChatCompletionRequest", "GuardrailsChatCompletionRequest"):
        model_cls = getattr(schema_module, name, None)
        if model_cls is not None:
            ensure_response_format_field(model_cls)

    original = api_module.chat_completion
    app = getattr(api_module, "app", None)
    if app is not None and hasattr(app, "add_middleware"):
        already = any(
            getattr(mw, "cls", None) is _CaptureResponseFormat
            for mw in getattr(app, "user_middleware", [])
        )
        if not already:
            app.add_middleware(_CaptureResponseFormat)

    async def chat_completion(body: Any, request: Any) -> Any:
        attach_response_format(body)
        result = await original(body, request)
        return rewrite_completion(result, current_response_format(body))

    setattr(chat_completion, _PATCHED, True)
    api_module.chat_completion = chat_completion
    for route in getattr(getattr(api_module, "app", None), "routes", []):
        if getattr(route, "path", None) != "/v1/chat/completions":
            continue
        methods = getattr(route, "methods", None) or set()
        if methods and "POST" not in methods:
            continue
        route.endpoint = chat_completion
        dependant = getattr(route, "dependant", None)
        if dependant is not None:
            dependant.call = chat_completion
    setattr(api_module, _PATCHED, True)
    _log.info("NeMo structured output patch applied", extra={"event": "structured_output"})
    return True


def _is_structured(response_format: Any) -> bool:
    return isinstance(response_format, dict) and response_format.get("type") in _STRUCTURED_TYPES


class _CaptureResponseFormat:
    """Stash ``response_format`` before NeMo's schema drops unknown JSON fields."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope.get("type") != "http" or scope.get("path") != "/v1/chat/completions":
            await self.app(scope, receive, send)
            return
        chunks: list[bytes] = []
        while True:
            message = await receive()
            if message["type"] != "http.request":
                break
            chunks.append(message.get("body", b""))
            if not message.get("more_body", False):
                break
        raw = b"".join(chunks)
        response_format = None
        try:
            parsed = json.loads(raw.decode("utf-8") or "{}")
            if isinstance(parsed, dict):
                response_format = parsed.get("response_format")
        except (UnicodeError, json.JSONDecodeError):
            response_format = None
        token = _current_response_format.set(response_format if _is_structured(response_format) else None)
        sent = False

        async def replay() -> dict:
            nonlocal sent
            if sent:
                return {"type": "http.disconnect"}
            sent = True
            return {"type": "http.request", "body": raw, "more_body": False}

        try:
            await self.app(scope, replay, send)
        finally:
            _current_response_format.reset(token)
