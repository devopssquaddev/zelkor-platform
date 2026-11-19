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


def _norm(text: str) -> str:
    return " ".join((text or "").replace("\u2019", "'").split()).strip().lower()


def parse_rail_refusal(flows: str) -> str:
    """The `bot refuse to respond` text from a rendered NeMo flows.co, or "" when absent."""
    import json
    import re

    m = re.search(r'define bot refuse to respond\s*\n\s*("(?:[^"\\]|\\.)*")', flows or "")
    return json.loads(m.group(1)) if m else ""


def is_rail_refusal(text: str, refusal: str) -> bool:
    """True only when the reply is the rail's configured refusal, not the model's own wording.

    A model that refuses by itself ("I'm sorry, but I can't help with that.") would pass a
    refusal-shaped check even when the rail never fired (S-12, catalog 2026-10-28)."""
    return bool(_norm(refusal)) and _norm(text) == _norm(refusal)

