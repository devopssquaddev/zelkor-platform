"""Shared helpers for Envoy AI Gateway / NeMo intercept tests."""


def assistant_text(body: dict) -> str:
    """Extract assistant text from OpenAI or NeMo Guardrails response bodies."""
    choices = body.get("choices") or []
    if choices:
        message = choices[0].get("message") or {}
        text = message.get("content") or message.get("refusal") or ""
        if text:
            return text

    messages = body.get("messages") or []
    for message in reversed(messages):
        if message.get("role") == "assistant":
            text = message.get("content") or message.get("refusal") or ""
            if text:
                return text

    return body.get("content") or ""


def has_assistant_reply(body: dict) -> bool:
    return bool(assistant_text(body).strip())
