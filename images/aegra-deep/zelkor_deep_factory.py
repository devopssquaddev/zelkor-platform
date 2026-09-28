"""Deploy-first factory: agent.json + AGENTS.md → create_deep_agent.

Model rewrite always uses ChatOpenAI + OPENAI_BASE_URL + consumer key.
Never set ANTHROPIC_API_KEY.
"""
from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("zelkor-deep-factory")

APP = Path(os.getenv("ZELKOR_AGENT_ROOT", "/app"))

try:
    from langchain_core.runnables import RunnableConfig
except ImportError:  # pragma: no cover
    RunnableConfig = dict  # type: ignore[misc,assignment]

try:
    from langgraph_sdk.runtime import ServerRuntime
except ImportError:  # pragma: no cover
    ServerRuntime = Any  # type: ignore[misc,assignment]


def load_json(path: Path) -> Any:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def graph_id_from_agent(agent: Dict[str, Any]) -> str:
    name = agent.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    return "agent"


def wants_sandbox(agent: Dict[str, Any]) -> bool:
    backend = agent.get("backend")
    if backend is None:
        runtime = agent.get("runtime")
        if isinstance(runtime, dict):
            backend = runtime.get("backend")
    if isinstance(backend, str):
        return backend.strip().lower() in ("sandbox", "gvisor")
    if isinstance(backend, dict):
        kind = str(backend.get("type") or "").strip().lower()
        if kind in ("sandbox", "gvisor"):
            return True
        if backend.get("sandbox") is True:
            return True
        cfg = backend.get("sandbox_config")
        return bool(cfg)
    return False


def _strip_provider(raw: str) -> str:
    text = (raw or "").strip()
    if ":" in text and not text.startswith("http"):
        _, rest = text.split(":", 1)
        return rest.strip() or text
    return text


def model_id_from_agent(agent: Dict[str, Any]) -> str:
    env_default = (os.getenv("DEFAULT_LLM_MODEL") or "").strip()
    raw: Any = agent.get("model")
    runtime = agent.get("runtime")
    if raw is None and isinstance(runtime, dict):
        model = runtime.get("model")
        if isinstance(model, dict):
            raw = model.get("model_id") or model.get("model")
        else:
            raw = model
    if isinstance(raw, dict):
        raw = raw.get("model_id") or raw.get("model") or ""
    stripped = _strip_provider(str(raw or ""))
    return env_default or stripped or "gpt-4o-mini"


def model_spec(agent: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "model": model_id_from_agent(agent),
        "base_url_env": "OPENAI_BASE_URL",
        "api_key_env": "OPENAI_API_KEY",
        "sets_anthropic_key": False,
        "anthropic_env_present": bool(os.getenv("ANTHROPIC_API_KEY")),
    }


def mcp_servers_from_tools(tools: Any) -> List[Dict[str, str]]:
    if tools is None:
        return []
    rows = tools
    if isinstance(tools, dict):
        rows = tools.get("tools") or tools.get("mcp") or tools.get("servers") or []
    if not isinstance(rows, list):
        return []
    out: List[Dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        url = (row.get("url") or row.get("mcp_server_url") or "").strip()
        name = (row.get("name") or row.get("mcp_server_name") or "").strip()
        if not url:
            continue
        if not name:
            name = f"mcp{len(out)}"
        out.append({"name": name, "url": url})
    return out


def _canonical_mcp_url() -> str:
    base = os.getenv("MCP_URL", "").rstrip("/")
    if not base:
        return ""
    return f"{base}/mcp"


def _normalize_mcp_url(raw: str) -> str:
    text = (raw or "").strip().rstrip("/")
    if not text:
        return ""
    if text.endswith("/mcp"):
        return text
    return f"{text}/mcp"


def validate_mcp_servers(servers: List[Dict[str, str]]) -> None:
    """Refuse tools.json entries that are not the platform MCP_URL hop."""
    expected = _canonical_mcp_url()
    if not servers:
        return
    if not expected:
        raise RuntimeError(
            "tools.json declares MCP servers but MCP_URL is not set; "
            "Deep Agents may only use {MCP_URL}/mcp"
        )
    for srv in servers:
        got = _normalize_mcp_url(srv.get("url") or "")
        if got != expected.rstrip("/"):
            name = srv.get("name") or "?"
            raise RuntimeError(
                f"tools.json MCP server {name!r} must use {expected!r} only (got {srv.get('url')!r})"
            )


def build_chat_model(agent: Dict[str, Any]) -> Any:
    from langchain_openai import ChatOpenAI

    spec = model_spec(agent)
    base = (os.getenv("OPENAI_BASE_URL") or "").strip() or None
    key = (os.getenv("OPENAI_API_KEY") or "").strip() or "unused"
    return ChatOpenAI(model=spec["model"], base_url=base, api_key=key)


def factory_kwargs(root: Path | None = None) -> Dict[str, Any]:
    base = root or APP
    agent = load_json(base / "agent.json") or {}
    if not isinstance(agent, dict):
        agent = {}
    agents_md = (base / "AGENTS.md").read_text(encoding="utf-8") if (base / "AGENTS.md").is_file() else ""
    tools_doc = load_json(base / "tools.json")
    kwargs: Dict[str, Any] = {
        "name": graph_id_from_agent(agent),
        "system_prompt": agents_md or None,
        "sandbox": wants_sandbox(agent),
        "mcp_servers": mcp_servers_from_tools(tools_doc),
        "model_spec": model_spec(agent),
        "skills_dir": str(base / "skills") if (base / "skills").is_dir() else "",
        "agent": agent,
    }
    return kwargs


async def _load_tools_from_session(session) -> list:
    from langchain_mcp_adapters.tools import convert_mcp_tool_to_langchain_tool

    result = await session.list_tools()
    specs = list(getattr(result, "tools", None) or [])
    return [convert_mcp_tool_to_langchain_tool(session, spec) for spec in specs]


@asynccontextmanager
async def _deep_mcp_session(bearer: str):
    from mcp_inject import _mcp_client_session

    async with _mcp_client_session(bearer) as session:
        yield session


def build_graph(root: Path | None = None, *, tools: Optional[list] = None) -> Any:
    from deepagents import create_deep_agent

    base = root or APP
    kwargs = factory_kwargs(base)
    agent = kwargs["agent"]
    create: Dict[str, Any] = {
        "model": build_chat_model(agent),
        "name": kwargs["name"],
    }
    if kwargs["system_prompt"]:
        create["system_prompt"] = kwargs["system_prompt"]
    backend = None
    if kwargs["sandbox"]:
        from zelkor_gvisor_backend import SKILLS_VIRTUAL_PATH, ZelkorGvisorBackend

        backend = ZelkorGvisorBackend()
        create["backend"] = backend
    if kwargs["skills_dir"]:
        host_skills = kwargs["skills_dir"].replace("\\", "/")
        if backend is not None:
            virt = backend.seed_host_dir(host_skills, SKILLS_VIRTUAL_PATH)
            if virt:
                create["skills"] = [virt]
        else:
            create["skills"] = [host_skills]
    if tools:
        create["tools"] = tools
    logger.info(
        "deep agent graph=%s sandbox=%s tools=%s",
        kwargs["name"],
        bool(kwargs["sandbox"]),
        len(tools or []),
        extra={"event": "graph_build", "graph_id": kwargs["name"]},
    )
    return create_deep_agent(**create)


def graph(config: RunnableConfig, runtime: ServerRuntime) -> Any:
    """Aegra deploy-first factory: MCP session only for threads.create_run."""
    kwargs = factory_kwargs()
    validate_mcp_servers(kwargs["mcp_servers"])
    access = getattr(runtime, "access_context", "") or ""

    if access != "threads.create_run":
        return build_graph(tools=[])

    if not kwargs["mcp_servers"]:
        return build_graph(tools=[])

    try:
        from mcp_inject import inbound_authorization
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("mcp_inject not available in deep image") from exc

    bearer = inbound_authorization(config if isinstance(config, dict) else None)
    if not bearer:
        logger.warning(
            "Deep factory: no MCP bearer for threads.create_run; graph runs without MCP tools"
        )
        return build_graph(tools=[])

    @asynccontextmanager
    async def _run_with_tools():
        async with _deep_mcp_session(bearer) as session:
            tools = await _load_tools_from_session(session)
            yield build_graph(tools=tools)

    return _run_with_tools()


graph.__annotations__ = {"config": RunnableConfig, "runtime": ServerRuntime}
