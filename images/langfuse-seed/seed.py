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
VALKEY_HOST = os.getenv("VALKEY_HOST", "").strip()
VALKEY_PORT = int(os.getenv("VALKEY_PORT", "6379") or "6379")
VALKEY_PASSWORD = os.getenv("VALKEY_PASSWORD", "")
EXTRA_PROJECTS_RAW = os.getenv("LANGFUSE_EXTRA_PROJECTS", "").strip()
SEED_ADMIN = os.getenv("SEED_ADMIN", "").lower() in ("1", "true", "yes")
SEED_INIT = os.getenv("SEED_INIT", "").lower() in ("1", "true", "yes")
ORG_NAME = os.getenv("LANGFUSE_ORG_NAME", "").strip()
PROJECT_NAME = os.getenv("LANGFUSE_PROJECT_NAME", "").strip()
INIT_USER_EMAIL = os.getenv("LANGFUSE_INIT_USER_EMAIL", "").strip()
# Cold Langfuse (Prisma + ClickHouse) exceeds the old 60s window.
HEALTH_ATTEMPTS = int(os.getenv("LANGFUSE_HEALTH_ATTEMPTS", "180"))
INIT_SETTLE_SEC = float(os.getenv("LANGFUSE_INIT_SETTLE_SEC", "2"))
ADMIN_EMAIL = os.getenv("LANGFUSE_ADMIN_EMAIL", "").strip()
ADMIN_PASSWORD = os.getenv("LANGFUSE_ADMIN_PASSWORD", "")
ADMIN_NAME = os.getenv("LANGFUSE_ADMIN_NAME", "Admin").strip() or "Admin"
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
    auth: bool = True,
) -> Any:
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if auth:
        headers["Authorization"] = _auth_header(public_key, secret_key)
    req = urllib.request.Request(
        f"{LANGFUSE_HOST}{path}",
        data=data,
        headers=headers,
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


def wait_healthy(attempts: int | None = None) -> None:
    last = ""
    n = HEALTH_ATTEMPTS if attempts is None else attempts
    for _ in range(n):
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


def _lookup_user_id(email: str) -> Optional[str]:
    if not email or not DATABASE_URL or psycopg is None:
        return None
    try:
        with psycopg.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id FROM users WHERE lower(email) = lower(%s) LIMIT 1",
                    (email,),
                )
                row = cur.fetchone()
                return str(row[0]) if row else None
    except Exception as exc:
        logger.debug("user lookup skipped: %s", exc)
        return None


def seed_init_project_sql() -> None:
    """Postgres-first init org/project/api_keys (replaces Langfuse LANGFUSE_INIT_* env)."""
    if not SEED_INIT:
        return
    if not DATABASE_URL or not ORG_ID or not LANGFUSE_SALT:
        raise RuntimeError("SEED_INIT requires DATABASE_URL, LANGFUSE_ORG_ID, LANGFUSE_SALT")
    if not PROJECT_ID or not PUBLIC_KEY or not SECRET_KEY:
        raise RuntimeError("SEED_INIT requires LANGFUSE_PROJECT_ID, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY")
    if psycopg is None:
        raise RuntimeError("psycopg is required to seed Langfuse init project")
    extra_pks = {p["publicKey"] for p in parse_extra_projects(EXTRA_PROJECTS_RAW)}
    if PUBLIC_KEY in extra_pks:
        raise RuntimeError("langfuse.init.projectPublicKey must not match an extraProjects publicKey")
    org_name = ORG_NAME or ORG_ID
    project_name = PROJECT_NAME or PROJECT_ID
    owner_email = INIT_USER_EMAIL or ADMIN_EMAIL
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO organizations (id, name, created_at, updated_at)
                VALUES (%s, %s, NOW(), NOW())
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    updated_at = NOW()
                """,
                (ORG_ID, org_name),
            )
            cur.execute(
                """
                INSERT INTO projects (id, org_id, name, created_at, updated_at, has_traces)
                VALUES (%s, %s, %s, NOW(), NOW(), false)
                ON CONFLICT (id) DO UPDATE SET
                    org_id = EXCLUDED.org_id,
                    name = EXCLUDED.name,
                    updated_at = NOW(),
                    deleted_at = NULL
                """,
                (PROJECT_ID, ORG_ID, project_name),
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
                    f"Zelkor init project {PROJECT_ID}",
                    PUBLIC_KEY,
                    hashed_secret_key(SECRET_KEY),
                    display_secret_key(SECRET_KEY),
                    PROJECT_ID,
                    fast_hashed_secret_key(SECRET_KEY, LANGFUSE_SALT),
                ),
            )
            user_id = _lookup_user_id(owner_email) if owner_email else None
            if user_id:
                org_membership_id = f"orgmem{uuid.uuid4().hex[:20]}"
                cur.execute(
                    """
                    INSERT INTO organization_memberships (
                        id, org_id, user_id, role, created_at, updated_at
                    )
                    VALUES (%s, %s, %s, 'OWNER', NOW(), NOW())
                    ON CONFLICT (org_id, user_id) DO UPDATE SET
                        role = 'OWNER',
                        updated_at = NOW()
                    RETURNING id
                    """,
                    (org_membership_id, ORG_ID, user_id),
                )
                row = cur.fetchone()
                org_membership_id = str(row[0]) if row else org_membership_id
                cur.execute(
                    """
                    INSERT INTO project_memberships (
                        project_id, user_id, created_at, updated_at, org_membership_id, role
                    )
                    VALUES (%s, %s, NOW(), NOW(), %s, 'OWNER')
                    ON CONFLICT (project_id, user_id) DO UPDATE SET
                        role = 'OWNER',
                        org_membership_id = EXCLUDED.org_membership_id,
                        updated_at = NOW()
                    """,
                    (PROJECT_ID, user_id, org_membership_id),
                )
        conn.commit()
    logger.info(
        "seeded init org=%s project=%s public_key=%s",
        ORG_ID,
        PROJECT_ID,
        PUBLIC_KEY,
        extra={"event": "init_project_sql"},
    )


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


def project_key_in_db(public_key: str) -> bool:
    return project_key_bound(public_key, "")


def project_key_bound(public_key: str, project_id: str) -> bool:
    """True when the init/extra public key exists and is bound to project_id (if given)."""
    if not public_key or not DATABASE_URL or psycopg is None:
        return False
    try:
        with psycopg.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                if project_id:
                    cur.execute(
                        """
                        SELECT 1 FROM api_keys
                        WHERE public_key = %s AND project_id = %s
                        LIMIT 1
                        """,
                        (public_key, project_id),
                    )
                else:
                    cur.execute(
                        "SELECT 1 FROM api_keys WHERE public_key = %s LIMIT 1",
                        (public_key,),
                    )
                return cur.fetchone() is not None
    except Exception as exc:
        logger.debug("api_keys lookup skipped: %s", exc)
        return False


def _encode_resp(parts: List[str]) -> bytes:
    chunks = [f"*{len(parts)}\r\n".encode("utf-8")]
    for part in parts:
        payload = part.encode("utf-8")
        chunks.append(f"${len(payload)}\r\n".encode("utf-8"))
        chunks.append(payload)
        chunks.append(b"\r\n")
    return b"".join(chunks)


def _valkey_roundtrip(parts: List[str]) -> bytes:
    import socket

    with socket.create_connection((VALKEY_HOST, VALKEY_PORT), timeout=5) as sock:
        if VALKEY_PASSWORD:
            sock.sendall(_encode_resp(["AUTH", VALKEY_PASSWORD]))
            auth = sock.recv(256)
            if auth.startswith(b"-"):
                raise RuntimeError(f"valkey AUTH failed: {auth!r}")
        sock.sendall(_encode_resp(parts))
        chunks: List[bytes] = []
        while True:
            piece = sock.recv(4096)
            if not piece:
                break
            chunks.append(piece)
            if len(piece) < 4096:
                break
    return b"".join(chunks)


def valkey_del(key: str) -> bool:
    if not VALKEY_HOST or not key:
        return False
    try:
        reply = _valkey_roundtrip(["DEL", key])
        return reply.startswith(b":") and not reply.startswith(b":0")
    except Exception as exc:
        logger.warning("valkey DEL %s failed: %s", key, exc)
        return False


def valkey_keys(pattern: str) -> List[str]:
    if not VALKEY_HOST or not pattern:
        return []
    try:
        reply = _valkey_roundtrip(["KEYS", pattern])
    except Exception as exc:
        logger.warning("valkey KEYS %s failed: %s", pattern, exc)
        return []
    if reply.startswith(b"-"):
        return []
    text = reply.decode("utf-8", errors="replace")
    if pattern == "api-key:*":
        return list(dict.fromkeys(re.findall(r"api-key:[0-9a-f]{64}", text)))
    return list(dict.fromkeys(re.findall(r"[^\r\n\s]+", text)))


def flush_all_api_key_cache() -> int:
    """Remove Langfuse negative API-key cache entries (api-key:*)."""
    deleted = 0
    for key in valkey_keys("api-key:*"):
        if valkey_del(key):
            deleted += 1
    return deleted


def invalidate_api_key_cache(secret_key: str) -> bool:
    """Drop the hashed cache entry; fall back to flushing all api-key:* keys."""
    if not secret_key:
        return False
    if not VALKEY_HOST:
        logger.warning("VALKEY_HOST unset; cannot clear Langfuse API-key cache")
        return False
    deleted = False
    if LANGFUSE_SALT:
        cache_key = f"api-key:{fast_hashed_secret_key(secret_key, LANGFUSE_SALT)}"
        deleted = valkey_del(cache_key)
        if deleted:
            logger.info(
                "cleared Langfuse API-key negative cache",
                extra={"event": "api_key_cache_cleared"},
            )
            return True
    else:
        logger.warning("LANGFUSE_SALT unset; flushing all api-key:* cache entries")
    flushed = flush_all_api_key_cache()
    if flushed:
        logger.info(
            "cleared %s Langfuse api-key cache entries",
            flushed,
            extra={"event": "api_key_cache_flushed", "count": flushed},
        )
        return True
    if not deleted:
        logger.warning("unable to clear Langfuse API-key cache via Valkey")
    return deleted


def wait_project_api(project: Dict[str, str], attempts: int = 60) -> None:
    """Wait for Postgres key + live API auth. Flush Valkey negative cache on 401."""
    last = ""
    public_key = project["publicKey"]
    project_id = (project.get("id") or PROJECT_ID or "").strip()
    init_settled = False
    for _ in range(attempts):
        if DATABASE_URL and not project_key_bound(public_key, project_id):
            last = "api_keys row not bound to project"
            init_settled = False
            time.sleep(2)
            continue
        if not init_settled and INIT_SETTLE_SEC > 0:
            time.sleep(INIT_SETTLE_SEC)
            init_settled = True
        try:
            _request(
                "GET",
                "/api/public/llm-connections",
                public_key=public_key,
                secret_key=project["secretKey"],
            )
            return
        except Exception as exc:
            last = str(exc)
            if "401" in last and DATABASE_URL and project_key_bound(public_key, project_id):
                logger.warning(
                    "Langfuse public API returned 401 with live api_keys row; invalidating Valkey cache"
                )
                invalidate_api_key_cache(project["secretKey"])
            time.sleep(2)
    raise RuntimeError(f"Langfuse API key for project {project['id']} not live: {last}")


def _already_exists_detail(detail: str) -> bool:
    low = (detail or "").lower()
    return any(token in low for token in ("already", "exists", "taken", "duplicate", "unique"))


def _admin_exists_sql(email: str) -> bool:
    if not DATABASE_URL or psycopg is None:
        return False
    try:
        with psycopg.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM users WHERE lower(email) = lower(%s) LIMIT 1",
                    (email,),
                )
                return cur.fetchone() is not None
    except Exception as exc:
        logger.debug("admin sql lookup skipped: %s", exc)
        return False


def _signup(email: str, password: str, name: str) -> tuple[int, str]:
    body = json.dumps({"name": name, "email": email, "password": password}).encode("utf-8")
    req = urllib.request.Request(
        f"{LANGFUSE_HOST}/api/auth/signup",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=20, context=ctx) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, raw[:400]
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        return exc.code, detail


def seed_admin_user(email: str = "", password: str = "", name: str = "") -> str:
    email = (email or ADMIN_EMAIL).strip()
    password = password or ADMIN_PASSWORD
    name = (name or ADMIN_NAME).strip() or "Admin"
    if not email or not password:
        raise RuntimeError("LANGFUSE_ADMIN_EMAIL and LANGFUSE_ADMIN_PASSWORD required")
    if _admin_exists_sql(email):
        logger.info("admin already present", extra={"event": "admin_exists", "email": email})
        return "exists"
    status, detail = _signup(email, password, name)
    if status in (200, 201):
        logger.info("admin created", extra={"event": "admin_created", "email": email})
        return "created"
    if status in (409, 422) or _already_exists_detail(detail):
        logger.info("admin already present", extra={"event": "admin_exists", "email": email})
        return "exists"
    raise RuntimeError(f"signup failed {status}: {detail}")


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


def _armor_enabled() -> bool:
    extra = parse_extra_projects(EXTRA_PROJECTS_RAW)
    return bool(
        LANGFUSE_HOST
        and PUBLIC_KEY
        and SECRET_KEY
        and (SEED_CONNECTION or SEED_TOOLS or SEED_EVALS or extra)
    )


def run_bootstrap() -> None:
    """Ordered Langfuse bootstrap: health → admin → SQL init → extras → armor."""
    wait_healthy()
    if SEED_ADMIN:
        seed_admin_user()
    if SEED_INIT:
        seed_init_project_sql()
    if parse_extra_projects(EXTRA_PROJECTS_RAW):
        seed_extra_projects()
    if _armor_enabled():
        seed_armor(managed_projects())


def main() -> int:
    from zelkor_logging import configure_logging

    configure_logging("zelkor-langfuse-seed")
    if not LANGFUSE_HOST:
        logger.info("skip bootstrap: LANGFUSE_HOST unset")
        return 0
    if not (SEED_ADMIN or SEED_INIT or _armor_enabled()):
        logger.info("skip bootstrap: no admin, init, or armor steps enabled")
        return 0
    run_bootstrap()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
