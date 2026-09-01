"""Project shape: deploy-first (agent.json) vs code-first (graphs map)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


class DetectError(ValueError):
    pass


@dataclass(frozen=True)
class ProjectShape:
    kind: str  # "deploy-first" | "code-first"
    graph_id: str
    root: Path
    mcp_servers: tuple[dict[str, str], ...]
    mcp_inject: bool
    wants_sandbox: bool


def _load_json(path: Path) -> Any:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def graphs_map(root: Path) -> Optional[dict[str, Any]]:
    for name in ("langgraph.json", "aegra.json"):
        data = _load_json(root / name)
        if isinstance(data, dict):
            graphs = data.get("graphs")
            if isinstance(graphs, dict) and graphs:
                return graphs
    return None


def mcp_servers_from_tools(root: Path) -> list[dict[str, str]]:
    data = _load_json(root / "tools.json")
    if data is None:
        return []
    rows = data
    if isinstance(data, dict):
        rows = data.get("tools") or data.get("mcp") or data.get("servers") or []
    if not isinstance(rows, list):
        return []
    out: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        url = str(row.get("url") or row.get("mcp_server_url") or "").strip()
        name = str(row.get("name") or row.get("mcp_server_name") or "").strip()
        if not url:
            continue
        out.append({"name": name or f"mcp{len(out)}", "url": url})
    return out


def _agent_sandbox(agent: dict[str, Any]) -> bool:
    backend = agent.get("backend")
    if isinstance(backend, str):
        return backend.strip().lower() in ("sandbox", "gvisor")
    if isinstance(backend, dict):
        kind = str(backend.get("type") or "").strip().lower()
        return kind in ("sandbox", "gvisor") or bool(backend.get("sandbox") or backend.get("sandbox_config"))
    return False


def detect(root: Path, graph_id: str = "") -> ProjectShape:
    root = root.resolve()
    graphs = graphs_map(root)
    servers = tuple(mcp_servers_from_tools(root))
    listed = bool(servers)
    if graphs:
        keys = list(graphs.keys())
        if graph_id:
            if graph_id not in graphs and len(keys) > 1:
                raise DetectError(f"--graph-id {graph_id} not in graphs map {keys}")
            gid = graph_id
        else:
            gid = keys[0]
        return ProjectShape(
            kind="code-first",
            graph_id=gid,
            root=root,
            mcp_servers=servers,
            mcp_inject=not listed,
            wants_sandbox=False,
        )
    agent_path = root / "agent.json"
    agents_md = root / "AGENTS.md"
    if agent_path.is_file() and agents_md.is_file():
        agent = _load_json(agent_path) or {}
        if not isinstance(agent, dict):
            agent = {}
        name = str(agent.get("name") or "").strip() or "agent"
        return ProjectShape(
            kind="deploy-first",
            graph_id=graph_id or name,
            root=root,
            mcp_servers=servers,
            mcp_inject=not listed,
            wants_sandbox=_agent_sandbox(agent),
        )
    raise DetectError(
        "not a Zelkor agent project: need agent.json + AGENTS.md, or langgraph.json / aegra.json with a graphs map"
    )


def customer_dockerfile(base_image: str) -> str:
    return f"FROM {base_image}\nCOPY . /app/\n"


def deploy_first_langgraph(graph_id: str) -> dict[str, Any]:
    return {
        "graphs": {graph_id: "./zelkor_deep_factory.py:graph"},
        "auth": {"path": "./tenant_auth.py:auth"},
    }


def helm_release_name(graph_id: str) -> str:
    raw = "".join(ch.lower() if ch.isalnum() else "-" for ch in graph_id).strip("-")
    return raw or "agent"


def should_attach_as_default(existing_route_names: list[str], this_release: str) -> bool:
    ours = f"{this_release}-zelkor-agent-route"
    others = [n for n in existing_route_names if n != ours]
    return not others
