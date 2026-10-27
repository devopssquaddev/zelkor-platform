"""Loopback egress on 127.0.0.1:8001 for the runtime container (CE-14).

``/run/active/v1/*`` → AI Gateway ``/v1``: consumer key, ``max_tokens`` cap, NeMo tools
stream rewrite, Langfuse/trace headers. ``/run/active/mcp`` → MCP gateway: the run's
verified JWT replaces whatever the runtime sent, ``tools/list`` is filtered and
``tools/call`` outside the agent's tool scope is refused before upstream, model-supplied
``tenant_id`` is stripped, every call becomes a TOOL span (+ CE-13 sandbox stamp) and an
``agent_step`` log with a 30 s wait beat. No active run → every request is refused.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .runs import RunContext, RunSlot
from .tracing import Tracing

logger = logging.getLogger("zelkor-sidecar")

HOP_HEADERS = {"host", "content-length", "connection", "keep-alive", "transfer-encoding",
               "te", "trailer", "upgrade", "proxy-authorization", "proxy-authenticate"}
# Identity headers the runtime must never set itself (claimToHeaders, Langfuse identity).
SPOOFABLE_PREFIXES = ("x-tenant-id", "x-zelkor-", "authorization", "traceparent", "tracestate", "baggage")
MCP_PASS_HEADERS = ("content-type", "accept", "mcp-session-id", "mcp-protocol-version", "last-event-id")
WAIT_BEAT_S = 30.0


def _truthy(raw: str) -> bool:
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class EgressConfig:
    llm_upstream: str
    mcp_upstream: str
    consumer_key: str = ""
    max_tokens: int = 0
    nemo_tools_no_stream: bool = False
    tool_prefixes: Tuple[str, ...] = ()
    tool_allow_all: bool = False
    timeout_s: float = 600.0
    extra: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "EgressConfig":
        prefixes = tuple(p.strip() for p in os.getenv("ZELKOR_TOOL_PREFIXES", "").split(",") if p.strip())
        return cls(
            llm_upstream=os.getenv("ZELKOR_LLM_UPSTREAM", "").rstrip("/"),
            mcp_upstream=os.getenv("ZELKOR_MCP_UPSTREAM", "").rstrip("/"),
            consumer_key=os.getenv("ZELKOR_CONSUMER_KEY", ""),
            max_tokens=int(os.getenv("ZELKOR_MAX_TOKENS", "0") or 0),
            nemo_tools_no_stream=_truthy(os.getenv("ZELKOR_NEMO_TOOLS_NO_STREAM", "false")),
            tool_prefixes=prefixes,
            tool_allow_all=_truthy(os.getenv("ZELKOR_TOOL_ALLOW_ALL", "false")),
        )


def tool_in_scope(name: str, cfg: EgressConfig) -> bool:
    """CE-9 scope, now server-side: allow-all, or ``<prefix>__`` match. Empty scope = none."""
    if cfg.tool_allow_all:
        return True
    return any(name.startswith(f"{p}__") for p in cfg.tool_prefixes)


def clamp_max_tokens(payload: Dict[str, Any], cap: int) -> None:
    """ZELKOR_MAX_TOKENS: set when absent, lower when above the cap; never raise it."""
    if cap <= 0:
        return
    if "max_completion_tokens" in payload:
        value = payload["max_completion_tokens"]
        payload["max_completion_tokens"] = cap if not isinstance(value, int) else min(value, cap)
        return
    value = payload.get("max_tokens")
    payload["max_tokens"] = cap if not isinstance(value, int) else min(value, cap)


def normalize_messages(payload: Dict[str, Any]) -> None:
    """Drop fields some runtimes add that the OpenAI chat schema does not allow.

    ``name`` on ``role: tool`` messages (CrewAI) is rejected by strict upstreams (422).
    """
    for msg in payload.get("messages") or []:
        if isinstance(msg, dict) and msg.get("role") == "tool":
            msg.pop("name", None)


def completion_to_sse(completion: Dict[str, Any]) -> bytes:
    """Re-stream one chat.completion as OpenAI-style chunks (+ [DONE])."""
    base = {"id": completion.get("id", f"chatcmpl-{uuid.uuid4().hex}"),
            "object": "chat.completion.chunk", "created": completion.get("created", int(time.time())),
            "model": completion.get("model", "")}
    out = []
    for choice in completion.get("choices") or []:
        msg = choice.get("message") or {}
        delta: Dict[str, Any] = {"role": msg.get("role", "assistant")}
        if msg.get("content") is not None:
            delta["content"] = msg["content"]
        if msg.get("tool_calls"):
            delta["tool_calls"] = [dict(tc, index=i) for i, tc in enumerate(msg["tool_calls"])]
        out.append({**base, "choices": [{"index": choice.get("index", 0), "delta": delta, "finish_reason": None}]})
        out.append({**base, "choices": [{"index": choice.get("index", 0), "delta": {},
                                         "finish_reason": choice.get("finish_reason", "stop")}]})
    if completion.get("usage"):
        out.append({**base, "choices": [], "usage": completion["usage"]})
    body = "".join(f"data: {json.dumps(chunk)}\n\n" for chunk in out) + "data: [DONE]\n\n"
    return body.encode("utf-8")


def parse_sse(raw: bytes) -> List[Tuple[str, str]]:
    """(event, data) pairs from an SSE body."""
    events, event, data = [], "message", []
    for line in raw.decode("utf-8", errors="replace").splitlines():
        if not line:
            if data:
                events.append((event, "\n".join(data)))
            event, data = "message", []
        elif line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            data.append(line[5:].lstrip())
    if data:
        events.append((event, "\n".join(data)))
    return events


def render_sse(events: List[Tuple[str, str]]) -> bytes:
    return "".join(f"event: {e}\ndata: {d}\n\n" for e, d in events).encode("utf-8")


def _clean_headers(headers: Dict[str, str], allowed: Optional[Tuple[str, ...]] = None) -> Dict[str, str]:
    out = {}
    for key, value in headers.items():
        low = key.lower()
        if low in HOP_HEADERS or low.startswith(SPOOFABLE_PREFIXES):
            continue
        if allowed is not None and low not in allowed:
            continue
        out[low] = value
    return out


class Egress:
    def __init__(self, slot: RunSlot, tracing: Tracing, cfg: EgressConfig, *, http: Any = None) -> None:
        self.slot = slot
        self.tracing = tracing
        self.cfg = cfg
        self._http = http

    async def client(self):
        if self._http is None:
            import httpx

            self._http = httpx.AsyncClient(timeout=httpx.Timeout(self.cfg.timeout_s, connect=10.0))
        return self._http

    # -- MCP --------------------------------------------------------------------------

    def _rewrite_request(self, ctx: RunContext, msg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Return a JSON-RPC error to send back instead of forwarding, or None to forward."""
        if msg.get("method") != "tools/call":
            return None
        params = msg.setdefault("params", {})
        name = str(params.get("name") or "")
        if not tool_in_scope(name, self.cfg):
            logger.warning("tool outside agent scope", extra={
                "event": "tools_call", "tool": name, "tenant_id": ctx.tenant_id, "status": "denied",
                "deny_reason": "agent_scope"})
            return {"jsonrpc": "2.0", "id": msg.get("id"),
                    "error": {"code": -32001, "message": f"tool {name} is not in this agent's tool scope"}}
        args = params.get("arguments")
        if isinstance(args, dict):
            args.pop("tenant_id", None)
        return None

    def _filter_tools(self, result: Dict[str, Any]) -> None:
        tools = result.get("tools")
        if isinstance(tools, list):
            result["tools"] = [t for t in tools if tool_in_scope(str(t.get("name", "")), self.cfg)]

    def _stamp(self, span: Any, result: Any) -> None:
        if not span.is_recording():
            return
        try:
            from opentelemetry import trace
            from sandbox_trace import stamp_sandbox_execution_span  # flat copy from images/aegra

            payload = result.get("content") if isinstance(result, dict) else result
            with trace.use_span(span, end_on_exit=False):
                stamp_sandbox_execution_span(payload)
        except Exception:  # noqa: BLE001 — stamping must never break the call
            logger.debug("sandbox stamp skipped", exc_info=True)

    async def mcp(self, request):
        from starlette.responses import JSONResponse, Response, StreamingResponse

        ctx = self.slot.active
        if ctx is None:
            return JSONResponse({"error": "no active run"}, status_code=409)
        if not self.cfg.mcp_upstream:
            return JSONResponse({"error": "MCP upstream not configured"}, status_code=503)
        http = await self.client()
        headers = _clean_headers(dict(request.headers), MCP_PASS_HEADERS)
        headers["authorization"] = ctx.bearer

        if request.method != "POST":  # GET server stream / DELETE session: pass through
            upstream = http.build_request(request.method, self.cfg.mcp_upstream, headers=headers)
            resp = await http.send(upstream, stream=True)
            import httpx

            async def relay():
                try:
                    async for chunk in resp.aiter_raw():
                        yield chunk
                except httpx.TransportError as exc:  # upstream dropped the stream: end it, do not 500
                    logger.warning("MCP stream closed by upstream: %s", type(exc).__name__,
                                   extra={"event": "mcp_stream", "run_id": ctx.run_id})
                finally:
                    await resp.aclose()

            return StreamingResponse(relay(), status_code=resp.status_code,
                                     headers=_clean_headers(dict(resp.headers)),
                                     background=None)

        body = json.loads(await request.body() or b"{}")
        batch = body if isinstance(body, list) else [body]
        for msg in batch:
            denied = self._rewrite_request(ctx, msg) if isinstance(msg, dict) else None
            if denied is not None:
                return JSONResponse(denied if not isinstance(body, list) else [denied])
        calls = {m.get("id"): m for m in batch if isinstance(m, dict) and m.get("method") == "tools/call"}
        lists = {m.get("id") for m in batch if isinstance(m, dict) and m.get("method") == "tools/list"}

        spans = {}
        started = time.monotonic()
        for mid, msg in calls.items():
            name = str(msg["params"].get("name") or "")
            ctx.tool_names.append(name)
            key = f"tool-{mid}-{uuid.uuid4().hex[:8]}"
            ctx.emit("custom", {"kind": "tool", "name": name, "phase": "start"}, key + "-start")
            logger.info("tool start", extra={"event": "agent_step", "kind": "tool", "phase": "start",
                                             "tool": name, "tenant_id": ctx.tenant_id, "run_id": ctx.run_id})
            cm = self.tracing.child(ctx, name, observation_type="tool")
            spans[mid] = (cm, cm.__enter__(), name, key)

        payload = json.dumps(body).encode("utf-8")
        send = asyncio.create_task(http.post(self.cfg.mcp_upstream, content=payload, headers=headers))
        while calls:
            done, _ = await asyncio.wait({send}, timeout=WAIT_BEAT_S)
            if done:
                break
            for _mid, (_cm, _span, name, key) in spans.items():
                elapsed = int(time.monotonic() - started)
                ctx.emit("custom", {"kind": "tool", "name": name, "phase": "wait", "elapsed_s": elapsed},
                         f"{key}-wait-{elapsed}")
                logger.info("tool wait", extra={"event": "agent_step", "kind": "tool", "phase": "wait",
                                                "tool": name, "elapsed_s": elapsed, "run_id": ctx.run_id})
        resp = await send
        raw = resp.content
        ctype = resp.headers.get("content-type", "")

        def visit(message: Dict[str, Any]) -> None:
            mid = message.get("id")
            result = message.get("result")
            if mid in lists and isinstance(result, dict):
                self._filter_tools(result)
            if mid in spans:
                cm, span, name, key = spans.pop(mid)
                is_error = "error" in message or bool(isinstance(result, dict) and result.get("isError"))
                if isinstance(result, dict) and result.get("isError"):
                    text = "".join(str(b.get("text", "")) for b in result.get("content") or [] if isinstance(b, dict))
                    logger.warning("MCP tool %s failed: %s", name, text.replace("\n", " ")[:200],
                                   extra={"event": "tools_call", "tool": name, "run_id": ctx.run_id, "status": "error"})
                if "error" in message:
                    err = message.get("error") or {}
                    logger.warning("tool error from MCP gateway", extra={
                        "event": "tools_call", "tool": name, "run_id": ctx.run_id, "status": "error",
                        "deny_reason": f"{err.get('code')}: {str(err.get('message'))[:200]}"})
                self._stamp(span, result)
                span.set_attribute("langfuse.observation.metadata.mcp.tool", name)
                if is_error:
                    span.set_attribute("langfuse.observation.level", "ERROR")
                cm.__exit__(None, None, None)
                ctx.emit("custom", {"kind": "tool", "name": name, "phase": "end", "is_error": is_error},
                         key + "-end")
                logger.info("tool end", extra={"event": "agent_step", "kind": "tool", "phase": "end",
                                               "tool": name, "is_error": is_error, "run_id": ctx.run_id,
                                               "elapsed_s": round(time.monotonic() - started, 3)})

        if "text/event-stream" in ctype:
            events = []
            for event, data in parse_sse(raw):
                try:
                    obj = json.loads(data)
                except ValueError:
                    events.append((event, data))
                    continue
                for message in obj if isinstance(obj, list) else [obj]:
                    if isinstance(message, dict):
                        visit(message)
                events.append((event, json.dumps(obj)))
            raw = render_sse(events)
        elif "json" in ctype and raw:
            obj = json.loads(raw)
            for message in obj if isinstance(obj, list) else [obj]:
                if isinstance(message, dict):
                    visit(message)
            raw = json.dumps(obj).encode("utf-8")
        if spans:
            logger.warning("no MCP response for tools/call", extra={
                "event": "tools_call", "run_id": ctx.run_id, "status": "error",
                "deny_reason": f"http {resp.status_code} {ctype or '-'} {len(raw)}B"})
        for mid in list(spans):  # no response for a call (transport error): close as error
            cm, span, name, key = spans.pop(mid)
            span.set_attribute("langfuse.observation.level", "ERROR")
            cm.__exit__(None, None, None)
            ctx.emit("custom", {"kind": "tool", "name": name, "phase": "end", "is_error": True}, key + "-end")
        out_headers = {k: v for k, v in resp.headers.items()
                       if k.lower() in ("content-type", "mcp-session-id", "mcp-protocol-version")}
        return Response(raw, status_code=resp.status_code, headers=out_headers)

    # -- LLM --------------------------------------------------------------------------

    async def llm(self, request):
        from starlette.responses import JSONResponse, Response, StreamingResponse

        ctx = self.slot.active
        if ctx is None:
            return JSONResponse({"error": "no active run"}, status_code=409)
        if not self.cfg.llm_upstream:
            return JSONResponse({"error": "LLM upstream not configured"}, status_code=503)
        tail = request.path_params.get("path", "")
        url = f"{self.cfg.llm_upstream}/{tail}"
        raw = await request.body()
        rewrite = False
        model = ""
        if raw and tail.endswith("chat/completions"):
            payload = json.loads(raw)
            model = str(payload.get("model") or "")
            clamp_max_tokens(payload, self.cfg.max_tokens)
            normalize_messages(payload)
            if payload.get("stream") and payload.get("tools") and self.cfg.nemo_tools_no_stream:
                payload["stream"] = False
                payload.pop("stream_options", None)
                rewrite = True
            raw = json.dumps(payload).encode("utf-8")
        http = await self.client()
        with self.tracing.child(ctx, f"chat {model}".strip(), observation_type="generation",
                                attrs={"gen_ai.request.model": model} if model else None) as span:
            headers = _clean_headers(dict(request.headers), ("content-type", "accept"))
            headers["authorization"] = f"Bearer {self.cfg.consumer_key}" if self.cfg.consumer_key else ""
            headers.update(self.tracing.propagation_headers(ctx, span))
            headers = {k: v for k, v in headers.items() if v}
            upstream = http.build_request(request.method, url, content=raw, headers=headers)
            resp = await http.send(upstream, stream=True)
            ctype = resp.headers.get("content-type", "")
            if rewrite and resp.status_code < 400 and "json" in ctype:
                completion = json.loads(await resp.aread())
                await resp.aclose()
                return Response(completion_to_sse(completion), media_type="text/event-stream")
            if "text/event-stream" in ctype:
                async def relay():
                    try:
                        async for chunk in resp.aiter_raw():
                            yield chunk
                    finally:
                        await resp.aclose()

                return StreamingResponse(relay(), status_code=resp.status_code, media_type="text/event-stream")
            body = await resp.aread()
            await resp.aclose()
            if resp.status_code >= 400:
                span.set_attribute("langfuse.observation.level", "ERROR")
            return Response(body, status_code=resp.status_code,
                            headers={"content-type": ctype or "application/json"})

    def app(self):
        from starlette.applications import Starlette
        from starlette.routing import Route

        return Starlette(routes=[
            Route("/run/active/v1/{path:path}", self.llm, methods=["GET", "POST"]),
            Route("/run/active/mcp", self.mcp, methods=["GET", "POST", "DELETE"]),
        ])
