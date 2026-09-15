"""Wrap identity for Mode B MCP: Aegra langgraph_auth_user only.

Bound at Pregel start so tools/call still sees the Auth user when
LangGraph get_config() is empty. Not a tracing helper.
"""
from __future__ import annotations

import contextvars
import logging
from typing import Any, Optional

logger = logging.getLogger("zelkor-wrap-identity")

_AUTH_USER: contextvars.ContextVar[Any] = contextvars.ContextVar(
    "zelkor_wrap_auth_user", default=None
)


def authorization_from_auth_user(user: Any) -> str:
    """Inbound Authorization header stashed by TenantAuth (Bearer jwt | dev:)."""
    if user is None:
        return ""
    if isinstance(user, dict):
        value = user.get("authorization") or user.get("Authorization")
        return str(value).strip() if value else ""
    value = getattr(user, "authorization", None) or getattr(user, "Authorization", None)
    if value:
        return str(value).strip()
    try:
        extra = user["authorization"]  # type: ignore[index]
        if extra:
            return str(extra).strip()
    except Exception:
        pass
    return ""


def identity_from_auth_user(user: Any) -> str:
    """tenant_id or identity on the Aegra Auth user (object or dict)."""
    if user is None:
        return ""
    if isinstance(user, dict):
        for key in ("tenant_id", "identity"):
            value = user.get(key)
            if value:
                return str(value)
        return ""
    for key in ("tenant_id", "identity"):
        value = getattr(user, key, None)
        if value:
            return str(value)
    try:
        for key in ("tenant_id", "identity"):
            value = user[key]  # type: ignore[index]
            if value:
                return str(value)
    except Exception:
        pass
    return ""


def auth_user_from_config(config: Optional[dict]) -> Any:
    if not isinstance(config, dict):
        return None
    configurable = config.get("configurable")
    if not isinstance(configurable, dict):
        return None
    return configurable.get("langgraph_auth_user")


def current_auth_user() -> Any:
    return _AUTH_USER.get()


def current_auth_identity() -> str:
    return identity_from_auth_user(current_auth_user())


def current_auth_authorization() -> str:
    return authorization_from_auth_user(current_auth_user())


def bind_auth_user(user: Any) -> contextvars.Token:
    return _AUTH_USER.set(user)


def reset_auth_user(token: contextvars.Token) -> None:
    _AUTH_USER.reset(token)


def _config_from_pregel_call(args: tuple, kwargs: dict) -> Optional[dict]:
    cfg = kwargs.get("config")
    if cfg is None and len(args) >= 2:
        cfg = args[1]
    return cfg if isinstance(cfg, dict) else None


def _run_with_pregel_identity(args: tuple, kwargs: dict, call):
    user = auth_user_from_config(_config_from_pregel_call(args, kwargs))
    token = bind_auth_user(user)
    try:
        return call()
    finally:
        reset_auth_user(token)


def patch_pregel() -> None:
    from langgraph.pregel import Pregel

    if getattr(Pregel, "_zelkor_wrap_identity", False):
        return

    orig_invoke = Pregel.invoke
    orig_ainvoke = Pregel.ainvoke
    orig_stream = Pregel.stream
    orig_astream = Pregel.astream
    orig_astream_events = Pregel.astream_events

    def invoke(self, *args, **kwargs):
        return _run_with_pregel_identity(args, kwargs, lambda: orig_invoke(self, *args, **kwargs))

    async def ainvoke(self, *args, **kwargs):
        async def _call():
            return await orig_ainvoke(self, *args, **kwargs)

        user = auth_user_from_config(_config_from_pregel_call(args, kwargs))
        token = bind_auth_user(user)
        try:
            return await _call()
        finally:
            reset_auth_user(token)

    def stream(self, *args, **kwargs):
        user = auth_user_from_config(_config_from_pregel_call(args, kwargs))
        token = bind_auth_user(user)
        try:
            yield from orig_stream(self, *args, **kwargs)
        finally:
            reset_auth_user(token)

    async def astream(self, *args, **kwargs):
        user = auth_user_from_config(_config_from_pregel_call(args, kwargs))
        token = bind_auth_user(user)
        try:
            async for item in orig_astream(self, *args, **kwargs):
                yield item
        finally:
            reset_auth_user(token)

    async def astream_events(self, *args, **kwargs):
        user = auth_user_from_config(_config_from_pregel_call(args, kwargs))
        token = bind_auth_user(user)
        try:
            async for item in orig_astream_events(self, *args, **kwargs):
                yield item
        finally:
            reset_auth_user(token)

    Pregel.invoke = invoke  # type: ignore[method-assign]
    Pregel.ainvoke = ainvoke  # type: ignore[method-assign]
    Pregel.stream = stream  # type: ignore[method-assign]
    Pregel.astream = astream  # type: ignore[method-assign]
    Pregel.astream_events = astream_events  # type: ignore[method-assign]
    Pregel._zelkor_wrap_identity = True  # type: ignore[attr-defined]
    logger.info("Pregel wrap-identity bind ok")
