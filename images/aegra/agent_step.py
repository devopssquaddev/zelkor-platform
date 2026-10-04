"""Live agent progress: INFO logs at node / model / tool start (no I/O bodies)."""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Optional
from uuid import UUID

try:
    from langchain_core.callbacks import BaseCallbackHandler
except ImportError:  # pragma: no cover

    class BaseCallbackHandler:  # type: ignore[no-redef]
        pass

_log = logging.getLogger("zelkor-aegra-wrap")
_WAIT_SEC = 30.0
_SKIP_CHAIN = (
    "LangGraph",
    "RunnableSequence",
    "RunnableLambda",
    "RunnableParallel",
    "RunnableEach",
    "ChannelWrite",
    "ChannelRead",
    "Pregel",
    "__start__",
    "__end__",
)
_recent: dict[tuple[str, str, str], float] = {}
_recent_lock = threading.Lock()


def _emit(kind: str, name: str, *, phase: str = "start", elapsed_s: int = 0) -> None:
    key = (kind, name, phase)
    now = time.monotonic()
    with _recent_lock:
        if now - _recent.get(key, 0.0) < 0.25 and phase != "wait":
            return
        _recent[key] = now
    extra: dict[str, Any] = {
        "event": "agent_step",
        "kind": kind,
        "step": name,
        "phase": phase,
        "elapsed_s": elapsed_s,
    }
    if phase == "wait":
        _log.info("agent step wait", extra=extra)
    else:
        _log.info("agent step", extra=extra)
    try:
        from langgraph.config import get_stream_writer

        get_stream_writer()(
            {"kind": kind, "name": name, "phase": phase, "elapsed_s": elapsed_s}
        )
    except Exception:
        pass


def _chain_name(serialized: Optional[dict], kwargs: dict) -> str:
    name = str(kwargs.get("name") or "").strip()
    if not name and isinstance(serialized, dict):
        name = str(serialized.get("name") or "").strip()
        if not name:
            ident = serialized.get("id")
            if isinstance(ident, (list, tuple)) and ident:
                name = str(ident[-1])
    return name


def _skip_chain(name: str) -> bool:
    if not name:
        return True
    if name in _SKIP_CHAIN:
        return True
    return name.startswith("Runnable") or name.startswith("Channel")


class _ToolHeartbeat:
    def __init__(self, name: str) -> None:
        self.name = name
        self.t0 = time.monotonic()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="zelkor-tool-wait", daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while not self._stop.wait(_WAIT_SEC):
            _emit("tool", self.name, phase="wait", elapsed_s=int(time.monotonic() - self.t0))

    def stop(self) -> None:
        self._stop.set()


class AgentStepCallback(BaseCallbackHandler):
    """LangChain callback: names only. No prompts, completions, or tool args."""

    raise_error = False

    def __init__(self) -> None:
        super().__init__()
        self._beats: dict[str, _ToolHeartbeat] = {}
        self._lock = threading.Lock()

    def on_chain_start(
        self,
        serialized: Optional[dict],
        inputs: Any,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        name = _chain_name(serialized, kwargs)
        if _skip_chain(name):
            return
        _emit("node", name)

    def on_chat_model_start(
        self,
        serialized: Optional[dict],
        messages: Any,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        name = _chain_name(serialized, kwargs) or "chat_model"
        _emit("model", name)

    def on_tool_start(
        self,
        serialized: Optional[dict],
        input_str: Any,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        name = str(kwargs.get("name") or _chain_name(serialized, kwargs) or "tool")
        _emit("tool", name)
        key = str(run_id)
        with self._lock:
            old = self._beats.pop(key, None)
            if old:
                old.stop()
            self._beats[key] = _ToolHeartbeat(name)

    def on_tool_end(self, output: Any, *, run_id: UUID, **kwargs: Any) -> None:
        self._stop_beat(run_id)

    def on_tool_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        self._stop_beat(run_id)

    def _stop_beat(self, run_id: UUID) -> None:
        with self._lock:
            beat = self._beats.pop(str(run_id), None)
        if beat:
            beat.stop()


_HANDLER = AgentStepCallback()


def emit_from_lc_event(item: Any) -> None:
    """Log from astream_events payloads (Aegra stream path)."""
    if not isinstance(item, dict):
        return
    ev = str(item.get("event") or "")
    name = str(item.get("name") or "").strip()
    raw_id = item.get("run_id") or item.get("id")
    try:
        run_id = raw_id if isinstance(raw_id, UUID) else UUID(str(raw_id))
    except Exception:
        run_id = UUID(int=0)
    if ev == "on_chain_start":
        if _skip_chain(name):
            return
        _emit("node", name)
    elif ev in ("on_chat_model_start", "on_llm_start"):
        _emit("model", name or "chat_model")
    elif ev == "on_tool_start":
        _HANDLER.on_tool_start(item.get("serialized"), None, run_id=run_id, name=name)
    elif ev == "on_tool_end":
        _HANDLER.on_tool_end(None, run_id=run_id)
    elif ev == "on_tool_error":
        _HANDLER.on_tool_error(RuntimeError("tool"), run_id=run_id)


def _merge_config(config: Any) -> Any:
    handler = _HANDLER
    if config is None:
        return {"callbacks": [handler]}
    if not isinstance(config, dict):
        return config
    cfg = dict(config)
    existing = cfg.get("callbacks")
    if existing is None:
        cfg["callbacks"] = [handler]
        return cfg
    if isinstance(existing, list):
        if handler not in existing:
            cfg["callbacks"] = [handler, *existing]
        return cfg
    mgr_add = getattr(existing, "add_handler", None)
    if callable(mgr_add):
        try:
            mgr_add(handler, inherit=True)
        except TypeError:
            mgr_add(handler)
        return cfg
    cfg["callbacks"] = [handler, existing]
    return cfg


def _inject_kwargs(args: tuple, kwargs: dict) -> tuple[tuple, dict]:
    kw = dict(kwargs)
    if "config" in kw:
        kw["config"] = _merge_config(kw["config"])
        return args, kw
    if len(args) >= 2:
        merged = _merge_config(args[1])
        return (args[0], merged, *args[2:]), kw
    kw["config"] = _merge_config(None)
    return args, kw


def install_agent_step_callback() -> None:
    try:
        from langgraph.pregel import Pregel
    except ImportError:
        return
    if getattr(Pregel, "_zelkor_agent_step", False):
        return

    orig_invoke = Pregel.invoke
    orig_ainvoke = Pregel.ainvoke
    orig_stream = Pregel.stream
    orig_astream = Pregel.astream
    orig_astream_events = Pregel.astream_events

    def invoke(self, *args, **kwargs):
        args, kwargs = _inject_kwargs(args, kwargs)
        return orig_invoke(self, *args, **kwargs)

    async def ainvoke(self, *args, **kwargs):
        args, kwargs = _inject_kwargs(args, kwargs)
        return await orig_ainvoke(self, *args, **kwargs)

    def stream(self, *args, **kwargs):
        args, kwargs = _inject_kwargs(args, kwargs)
        yield from orig_stream(self, *args, **kwargs)

    async def astream(self, *args, **kwargs):
        args, kwargs = _inject_kwargs(args, kwargs)
        async for item in orig_astream(self, *args, **kwargs):
            if isinstance(item, tuple) and len(item) >= 2 and item[0] in ("events", "event"):
                emit_from_lc_event(item[1])
            elif isinstance(item, dict) and item.get("event"):
                emit_from_lc_event(item)
            yield item

    async def astream_events(self, *args, **kwargs):
        args, kwargs = _inject_kwargs(args, kwargs)
        async for item in orig_astream_events(self, *args, **kwargs):
            emit_from_lc_event(item)
            yield item

    Pregel.invoke = invoke  # type: ignore[method-assign]
    Pregel.ainvoke = ainvoke  # type: ignore[method-assign]
    Pregel.stream = stream  # type: ignore[method-assign]
    Pregel.astream = astream  # type: ignore[method-assign]
    Pregel.astream_events = astream_events  # type: ignore[method-assign]
    Pregel._zelkor_agent_step = True  # type: ignore[attr-defined]
    _log.info("agent step callback ready")
