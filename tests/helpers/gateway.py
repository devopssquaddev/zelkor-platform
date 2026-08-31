"""Shared helpers for Envoy AI Gateway / NeMo intercept tests."""


def assistant_text(body: dict) -> str:
    """Extract assistant text from OpenAI or NeMo Guardrails response bodies."""
    choices = body.get("choices") or []
    if choices:
        message = choices[0].get("message") or {}
        text = (
            message.get("content")
            or message.get("refusal")
            or message.get("reasoning_content")
            or ""
        )
        if text:
            return text

    messages = body.get("messages") or []
    for message in reversed(messages):
        if message.get("role") == "assistant":
            text = (
                message.get("content")
                or message.get("refusal")
                or message.get("reasoning_content")
                or ""
            )
            if text:
                return text

    return body.get("content") or ""


def is_chat_completion(body: dict) -> bool:
    """True when the body is an OpenAI chat.completion with a choices[] message."""
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        return False
    message = choices[0].get("message")
    return isinstance(message, dict)


def has_assistant_reply(body: dict) -> bool:
    return bool(assistant_text(body).strip())


def looks_like_refusal(text: str) -> bool:
    """True for canned or model-generated safety refusals (not one exact string)."""
    lowered = (text or "").lower()
    return any(
        needle in lowered
        for needle in (
            "can't help",
            "cannot help",
            "can’t help",
            "i'm sorry",
            "i’m sorry",
            "sorry, but",
            "refus",
            "not able to",
            "unable to help",
            "i won't",
            "i will not",
        )
    )
