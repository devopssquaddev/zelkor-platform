"""Deploy-first factory: agent.json + AGENTS.md → create_deep_agent.

Model rewrite always uses ChatOpenAI + OPENAI_BASE_URL + consumer key.
Never set ANTHROPIC_API_KEY.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("zelkor-deep-factory")

APP = Path(os.getenv("ZELKOR_AGENT_ROOT", "/app"))


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
    }
    return kwargs


def _load_mcp_tools(servers: List[Dict[str, str]]) -> list:
    if not servers:
        return []
    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient
    except Exception:
        logger.warning("langchain-mcp-adapters not available; skip Mode A MCP tools")
        return []
    conf = {}
    for srv in servers:
        conf[srv["name"]] = {"url": srv["url"], "transport": "streamable_http"}
    try:
        client = MultiServerMCPClient(conf)
        get_tools = getattr(client, "get_tools", None)
        if get_tools is None:
            return []
        import asyncio
        import inspect

        result = get_tools()
        if inspect.isawaitable(result):
            result = asyncio.run(result)
        return list(result or [])
    except Exception:
        logger.exception("Mode A MCP tool load failed")
        return []


def build_graph(root: Path | None = None) -> Any:
    from deepagents import create_deep_agent

    base = root or APP
    agent = load_json(base / "agent.json") or {}
    if not isinstance(agent, dict):
        agent = {}
    kwargs = factory_kwargs(base)
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
    tools = _load_mcp_tools(kwargs["mcp_servers"])
    if tools:
        create["tools"] = tools
    return create_deep_agent(**create)


def graph():
    return build_graph()
