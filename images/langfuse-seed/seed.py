"""Idempotent Langfuse CE-3 surface seed (no inline Helm Python)."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import ssl
import time
import urllib.error
import urllib.request
import uuid
from base64 import b64encode
from typing import Any, Dict, List, Optional

try:
    import bcrypt
except ImportError:  # unit tests import helpers without the hasher
    bcrypt = None  # type: ignore[assignment]

try:
    import psycopg
except ImportError:  # unit tests import helpers without the binary driver
    psycopg = None  # type: ignore[assignment]

logger = logging.getLogger("zelkor-langfuse-seed")

LANGFUSE_HOST = os.getenv("LANGFUSE_HOST", "").rstrip("/")
PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY", "")
SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY", "")
CONNECTION_NAME = os.getenv("LANGFUSE_CONNECTION_NAME", "zelkor-ai-gateway")
AI_GATEWAY_BASE_URL = os.getenv("AI_GATEWAY_BASE_URL", "").rstrip("/")
CONSUMER_KEY = os.getenv("AI_GATEWAY_CONSUMER_KEY", "")
CUSTOM_MODELS = [m.strip() for m in os.getenv("LANGFUSE_CUSTOM_MODELS", "").split(",") if m.strip()]
SEED_CONNECTION = os.getenv("SEED_LLM_CONNECTION", "").lower() in ("1", "true", "yes")
SEED_TOOLS = os.getenv("SEED_MCP_TOOLS", "").lower() in ("1", "true", "yes")
SEED_EVALS = os.getenv("SEED_CODE_EVALUATORS", "").lower() in ("1", "true", "yes")
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
PROJECT_ID = os.getenv("LANGFUSE_PROJECT_ID", "").strip()
ORG_ID = os.getenv("LANGFUSE_ORG_ID", "").strip()
LANGFUSE_SALT = os.getenv("LANGFUSE_SALT", "").strip()
EXTRA_PROJECTS_RAW = os.getenv("LANGFUSE_EXTRA_PROJECTS", "").strip()
MCP_URL = os.getenv("MCP_URL", "").rstrip("/")
TOOL_NAME_OK = re.compile(r"^[a-zA-Z0-9._-]+$")
MCP_TENANT = os.getenv("MCP_SEED_TENANT", "seed")
MCP_AUTH_TOKEN = os.getenv("MCP_AUTH_TOKEN", "").strip()
NATIVE_PREFIXES = ("postgres__", "qdrant__", "sandbox__", "egress__")


def parse_extra_projects(raw: str) -> List[Dict[str, str]]:
    try:
        data = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    out: List[Dict[str, str]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        pid = str(item.get("id") or "").strip()
        public_key = str(item.get("publicKey") or item.get("public_key") or "").strip()
        secret_key = str(item.get("secretKey") or item.get("secret_key") or "").strip()
        name = str(item.get("name") or pid).strip()
        if pid and public_key and secret_key:
            out.append(
                {
                    "id": pid,
                    "name": name,
                    "publicKey": public_key,
                    "secretKey": secret_key,
                }
            )
    return out


def managed_projects() -> List[Dict[str, str]]:
    """init ∪ extraProjects. Armor seed loops this list."""
    extras = parse_extra_projects(EXTRA_PROJECTS_RAW)
    out: List[Dict[str, str]] = []
    seen: set[str] = set()
    if PROJECT_ID and PUBLIC_KEY and SECRET_KEY:
        out.append(
            {
                "id": PROJECT_ID,
                "name": PROJECT_ID,
                "publicKey": PUBLIC_KEY,
                "secretKey": SECRET_KEY,
            }
        )
        seen.add(PUBLIC_KEY)
    for proj in extras:
        if proj["publicKey"] in seen:
            continue
        seen.add(proj["publicKey"])
        out.append(proj)
    return out


def display_secret_key(secret: str) -> str:
    if len(secret) < 10:
        return secret[:3] + "..."
    return secret[:6] + "..." + secret[-4:]


def fast_hashed_secret_key(secret: str, salt: str) -> str:
    """Langfuse `createShaHash`: sha256(secret + sha256(salt).hexdigest())."""
    inner = hashlib.sha256(salt.encode("utf-8")).hexdigest()
    h = hashlib.sha256()
    h.update(secret.encode("utf-8"))
    h.update(inner.encode("utf-8"))
    return h.hexdigest()


def hashed_secret_key(secret: str) -> str:
    if bcrypt is None:
        raise RuntimeError("bcrypt is required to seed Langfuse API keys")
    return bcrypt.hashpw(secret.encode("utf-8"), bcrypt.gensalt(rounds=11)).decode("utf-8")


def extra_backend_names(raw: str) -> List[str]:
    try:
        data = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [str(item.get("name") or "") for item in data if isinstance(item, dict)]


def keep_mcp_tool(name: str, extras: List[str]) -> bool:
    if name.startswith(NATIVE_PREFIXES):
        return True
    return any(name.startswith(f"{prefix}__") for prefix in extras if prefix)


def to_openai_function(tool: dict) -> dict:
    llm = to_llm_tool(tool)
    return {
        "type": "function",
        "function": {
            "name": llm["name"],
            "description": llm["description"],
            "parameters": llm["parameters"],
        },
    }


def to_llm_tool(tool: dict) -> dict:
    """Langfuse Playground LlmTool row / prompt.config.tools (flat, not OpenAI-wrapped)."""
    params = tool.get("inputSchema") or tool.get("parameters") or {"type": "object", "properties": {}}
    if not isinstance(params, dict):
        params = {"type": "object", "properties": {}}
    if params.get("type") != "object":
        params = {"type": "object", "properties": params.get("properties") or {}}
    return {
        "name": str(tool.get("name") or ""),
        "description": str(tool.get("description") or ""),
        "parameters": params,
    }


def _auth_header(public_key: str = "", secret_key: str = "") -> str:
    token = b64encode(
        f"{public_key or PUBLIC_KEY}:{secret_key or SECRET_KEY}".encode("utf-8")
    ).decode("ascii")
    return f"Basic {token}"


def _request(
    method: str,
    path: str,
    body: Optional[dict] = None,
    *,
    public_key: str = "",
    secret_key: str = "",
) -> Any:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{LANGFUSE_HOST}{path}",
        data=data,
        headers={
            "Authorization": _auth_header(public_key, secret_key),
            "Content-Type": "application/json",
        },
        method=method,
    )
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=20, context=ctx) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise RuntimeError(f"{method} {path} -> {exc.code}: {detail}") from exc


def wait_healthy(attempts: int = 30) -> None:
    last = ""
    for _ in range(attempts):
        try:
            urllib.request.urlopen(f"{LANGFUSE_HOST}/api/public/health", timeout=5)
            logger.info("Langfuse healthy")
            return
        except Exception as exc:
            last = str(exc)
            logger.debug("Langfuse health retry: %s", exc)
            time.sleep(2)
    raise RuntimeError(f"Langfuse not healthy: {last}")


def existing_custom_models(*, public_key: str = "", secret_key: str = "") -> List[str]:
    try:
        rows = _request("GET", "/api/public/llm-connections", public_key=public_key, secret_key=secret_key)
    except Exception as exc:
        logger.info("llm-connections GET skipped (%s)", exc)
        return []
    data = rows.get("data") if isinstance(rows, dict) else rows
    if not isinstance(data, list):
        return []
    for row in data:
        if not isinstance(row, dict):
            continue
        if (row.get("provider") or row.get("name")) != CONNECTION_NAME:
            continue
        models = row.get("customModels") or row.get("custom_models") or []
        return [str(m).strip() for m in models if str(m).strip()]
    return []


def resolve_custom_models(configured: List[str], existing: List[str]) -> List[str]:
    """Helm-supplied ids win. Empty helm list must not wipe UI-added models."""
    if configured:
        return configured
    return existing


def seed_connection(project: Dict[str, str]) -> None:
    if not AI_GATEWAY_BASE_URL or not CONSUMER_KEY:
        logger.info("skip llm-connection: missing AI_GATEWAY_BASE_URL or consumer key")
        return
    models = resolve_custom_models(
        CUSTOM_MODELS,
        existing_custom_models(public_key=project["publicKey"], secret_key=project["secretKey"]),
    )
    payload = {
        "provider": CONNECTION_NAME,
        "adapter": "openai",
        "secretKey": CONSUMER_KEY,
        "baseURL": AI_GATEWAY_BASE_URL,
        "withDefaultModels": False,
        "customModels": models,
    }
    _request(
        "PUT",
        "/api/public/llm-connections",
        payload,
        public_key=project["publicKey"],
        secret_key=project["secretKey"],
    )
    logger.info(
        "seeded llm-connection %s project=%s -> %s models=%s",
        CONNECTION_NAME,
        project["id"],
        AI_GATEWAY_BASE_URL,
        models,
    )


def mcp_tools_list() -> List[Dict[str, Any]]:
    if not MCP_URL:
        return []
    headers = {
        "Content-Type": "application/json",
        "X-Tenant-ID": MCP_TENANT,
    }
    if MCP_AUTH_TOKEN:
        token = MCP_AUTH_TOKEN if MCP_AUTH_TOKEN.lower().startswith("bearer ") else f"Bearer {MCP_AUTH_TOKEN}"
        headers["Authorization"] = token
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}).encode("utf-8")
    req = urllib.request.Request(f"{MCP_URL}/mcp", data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return (data.get("result") or {}).get("tools") or []


def load_mcp_tools() -> List[Dict[str, Any]]:
    extras = extra_backend_names(os.getenv("MCP_EXTRA_BACKENDS", "[]"))
    last = ""
    tools: List[Dict[str, Any]] = []
    for _ in range(15):
        try:
            tools = mcp_tools_list()
            break
        except Exception as exc:
            last = str(exc)
            time.sleep(2)
    else:
        raise RuntimeError(f"MCP tools/list failed: {last}")
    return [
        to_llm_tool(t)
        for t in tools
        if keep_mcp_tool(t.get("name") or "", extras) and TOOL_NAME_OK.match(t.get("name") or "")
    ]


def seed_tools_for_project(project: Dict[str, str], saved: List[Dict[str, Any]]) -> None:
    upsert_llm_tools(saved, project["id"])
    _request(
        "POST",
        "/api/public/v2/prompts",
        {
            "name": "zelkor-mcp-tools",
            "type": "text",
            "prompt": "Zelkor MCP tool catalog. Playground execution is mocked.",
            "labels": ["production"],
            "config": {"tools": saved},
        },
        public_key=project["publicKey"],
        secret_key=project["secretKey"],
    )
    logger.info("seeded %s MCP tools into project %s", len(saved), project["id"])


def upsert_llm_tools(tools: List[Dict[str, Any]], project_id: str) -> None:
    """Playground saved-tools picker reads llm_tools. 4.24 has no public tools API."""
    if not DATABASE_URL or not project_id:
        raise RuntimeError("SEED_MCP_TOOLS requires DATABASE_URL and a project id")
    if psycopg is None:
        raise RuntimeError("psycopg is required to seed Langfuse llm_tools")
    sql = """
        INSERT INTO llm_tools (id, created_at, updated_at, project_id, name, description, parameters)
        VALUES (%s, NOW(), NOW(), %s, %s, %s, %s::jsonb)
        ON CONFLICT (project_id, name) DO UPDATE SET
            description = EXCLUDED.description,
            parameters = EXCLUDED.parameters,
            updated_at = NOW()
    """
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            for tool in tools:
                cur.execute(
                    sql,
                    (
                        f"cl{uuid.uuid4().hex}",
                        project_id,
                        tool["name"],
                        tool["description"],
                        json.dumps(tool["parameters"]),
                    ),
                )
        conn.commit()


def seed_extra_projects() -> None:
    """Upsert extra Langfuse projects + API keys (SQL; 4.24 project API needs an org key)."""
    projects = parse_extra_projects(EXTRA_PROJECTS_RAW)
    if not projects:
        return
    if not DATABASE_URL or not ORG_ID or not LANGFUSE_SALT:
        raise RuntimeError("LANGFUSE_EXTRA_PROJECTS requires DATABASE_URL, LANGFUSE_ORG_ID, LANGFUSE_SALT")
    if psycopg is None:
        raise RuntimeError("psycopg is required to seed extra Langfuse projects")
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            for proj in projects:
                cur.execute(
                    """
                    INSERT INTO projects (id, org_id, name, created_at, updated_at, has_traces)
                    VALUES (%s, %s, %s, NOW(), NOW(), false)
                    ON CONFLICT (id) DO UPDATE SET
                        name = EXCLUDED.name,
                        updated_at = NOW(),
                        deleted_at = NULL
                    """,
                    (proj["id"], ORG_ID, proj["name"]),
                )
                cur.execute(
                    """
                    INSERT INTO api_keys (
                        id, created_at, note, public_key, hashed_secret_key, display_secret_key,
                        project_id, fast_hashed_secret_key, scope, is_in_app_agent_key
                    )
                    VALUES (%s, NOW(), %s, %s, %s, %s, %s, %s, 'PROJECT', false)
                    ON CONFLICT (public_key) DO UPDATE SET
                        project_id = EXCLUDED.project_id,
                        hashed_secret_key = EXCLUDED.hashed_secret_key,
                        fast_hashed_secret_key = EXCLUDED.fast_hashed_secret_key,
                        display_secret_key = EXCLUDED.display_secret_key,
                        note = EXCLUDED.note
                    """,
                    (
                        f"clkf{uuid.uuid4().hex}",
                        f"Zelkor extra project {proj['id']}",
                        proj["publicKey"],
                        hashed_secret_key(proj["secretKey"]),
                        display_secret_key(proj["secretKey"]),
                        proj["id"],
                        fast_hashed_secret_key(proj["secretKey"], LANGFUSE_SALT),
                    ),
                )
                if PROJECT_ID:
                    cur.execute(
                        """
                        INSERT INTO project_memberships (
                            project_id, user_id, created_at, updated_at, org_membership_id, role
                        )
                        SELECT %s, user_id, NOW(), NOW(), org_membership_id, role
                        FROM project_memberships
                        WHERE project_id = %s
                        ON CONFLICT (project_id, user_id) DO NOTHING
                        """,
                        (proj["id"], PROJECT_ID),
                    )
        conn.commit()
    logger.info("seeded %s extra Langfuse project(s)", len(projects))


def ensure_init_key_on_project() -> None:
    """Keep the platform init public key on the init project (overlay must not steal it)."""
    if not DATABASE_URL or not PUBLIC_KEY or not PROJECT_ID:
        return
    if psycopg is None:
        raise RuntimeError("psycopg is required to bind the Langfuse init key")
    extra_pks = {p["publicKey"] for p in parse_extra_projects(EXTRA_PROJECTS_RAW)}
    if PUBLIC_KEY in extra_pks:
        raise RuntimeError("langfuse.init.projectPublicKey must not match an extraProjects publicKey")
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE api_keys
                SET project_id = %s
                WHERE public_key = %s AND (project_id IS DISTINCT FROM %s)
                """,
                (PROJECT_ID, PUBLIC_KEY, PROJECT_ID),
            )
            moved = cur.rowcount
        conn.commit()
    if moved:
        logger.info("moved init API key onto project %s", PROJECT_ID)


def seed_evaluators(project: Dict[str, str]) -> None:
    configs = [
        {
            "name": "zelkor-refusal-present",
            "dataType": "BOOLEAN",
            "description": "Blocked GENERATION observations include platform refusal text.",
        },
        {
            "name": "zelkor-mcp-prefix",
            "dataType": "BOOLEAN",
            "description": "Agent tool observations use a native MCP prefix (postgres__/qdrant__/sandbox__/egress__).",
        },
        {
            "name": "zelkor-tenant-userid",
            "dataType": "BOOLEAN",
            "description": "Agent traces stamp userId / tenant metadata.",
        },
    ]
    existing = _request(
        "GET",
        "/api/public/score-configs?limit=100",
        public_key=project["publicKey"],
        secret_key=project["secretKey"],
    )
    names = {c.get("name") for c in (existing.get("data") or [])}
    for cfg in configs:
        if cfg["name"] in names:
            continue
        _request(
            "POST",
            "/api/public/score-configs",
            cfg,
            public_key=project["publicKey"],
            secret_key=project["secretKey"],
        )
    logger.info("seeded code evaluator score-configs project=%s", project["id"])


def wait_project_api(project: Dict[str, str], attempts: int = 20) -> None:
    """Langfuse caches API keys; extra-project keys 401 until web/worker reload the row."""
    last = ""
    for _ in range(attempts):
        try:
            _request(
                "GET",
                "/api/public/llm-connections",
                public_key=project["publicKey"],
                secret_key=project["secretKey"],
            )
            return
        except Exception as exc:
            last = str(exc)
            time.sleep(2)
    raise RuntimeError(f"Langfuse API key for project {project['id']} not live: {last}")


def seed_armor(projects: List[Dict[str, str]]) -> None:
    saved: List[Dict[str, Any]] = []
    if SEED_TOOLS:
        saved = load_mcp_tools()
    for project in projects:
        wait_project_api(project)
        if SEED_CONNECTION:
            seed_connection(project)
        if SEED_TOOLS:
            seed_tools_for_project(project, saved)
        if SEED_EVALS:
            seed_evaluators(project)


def main() -> int:
    from zelkor_logging import configure_logging

    configure_logging("zelkor-langfuse-seed")
    extra = parse_extra_projects(EXTRA_PROJECTS_RAW)
    if not LANGFUSE_HOST or not PUBLIC_KEY or not SECRET_KEY:
        logger.info("skip: Langfuse host or keys unset")
        return 0
    if not (SEED_CONNECTION or SEED_TOOLS or SEED_EVALS or extra):
        logger.info("skip: all seed knobs off")
        return 0
    wait_healthy()
    if extra or (DATABASE_URL and PUBLIC_KEY and PROJECT_ID):
        seed_extra_projects()
        ensure_init_key_on_project()
    seed_armor(managed_projects())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
