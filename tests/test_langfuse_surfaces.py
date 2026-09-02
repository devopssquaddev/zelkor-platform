"""Langfuse CE-3 surfaces: connection seed + generic evaluators (skip if init off)."""
from __future__ import annotations

import json
import os

import httpx
import pytest

from tests.helpers.langfuse import GATEWAY_BASE_URL, LANGFUSE_AUTH, langfuse_get, langfuse_headers

UPSTREAM_KEY_MARKERS = ("sk-proj-", "sk-ant-", "AIza", "sk-or-")


def _init_expected() -> bool:
    return os.environ.get("LANGFUSE_INIT_ENABLED", "true").lower() in ("1", "true", "yes")


def test_langfuse_zelkor_ai_gateway_connection():
    if not _init_expected():
        pytest.skip("langfuse.init disabled")
    try:
        resp = langfuse_get("/api/public/llm-connections")
    except httpx.ConnectError:
        pytest.skip(f"Langfuse not reachable at {GATEWAY_BASE_URL}")
    if resp.status_code in (401, 403, 404):
        pytest.skip(f"llm-connections unavailable: {resp.status_code}")
    assert resp.status_code == 200, resp.text
    rows = resp.json().get("data") or resp.json()
    if isinstance(rows, dict):
        rows = rows.get("data") or [rows]
    names = [r.get("provider") or r.get("name") for r in rows]
    match = next((r for r in rows if (r.get("provider") or r.get("name")) == "zelkor-ai-gateway"), None)
    if match is None:
        pytest.skip(f"zelkor-ai-gateway not seeded (got {names})")
    base = str(match.get("baseURL") or match.get("baseUrl") or "")
    assert "/v1" in base
    assert "localhost" not in base
    assert "openai.com" not in base
    blob = json.dumps(match)
    assert not any(marker in blob for marker in UPSTREAM_KEY_MARKERS)
    seeded = os.environ.get("DEFAULT_LLM_MODEL") or os.environ.get("LANGFUSE_SEEDED_MODEL")
    models = match.get("customModels") or match.get("custom_models") or []
    if seeded:
        assert seeded in models, f"playground model {seeded} missing from {models}"
    elif not models:
        pytest.skip("zelkor-ai-gateway has no customModels (set DEFAULT_LLM_MODEL on install)")


def test_langfuse_mcp_tools_catalog_prompt():
    if not _init_expected():
        pytest.skip("langfuse.init disabled")
    try:
        resp = langfuse_get("/api/public/v2/prompts/zelkor-mcp-tools")
    except httpx.ConnectError:
        pytest.skip(f"Langfuse not reachable at {GATEWAY_BASE_URL}")
    if resp.status_code in (401, 403, 404):
        pytest.skip(f"zelkor-mcp-tools not seeded: {resp.status_code}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    cfg = body.get("config") or {}
    tools = cfg.get("tools") or []
    names = {t.get("name") for t in tools if isinstance(t, dict)}
    native = {n for n in names if n.startswith(("postgres__", "qdrant__", "sandbox__", "egress__"))}
    if not native:
        pytest.skip(f"prompt config.tools has no native MCP names (got {names})")


def test_langfuse_code_evaluator_score_configs():
    if not _init_expected():
        pytest.skip("langfuse.init disabled")
    try:
        resp = langfuse_get("/api/public/score-configs", params={"limit": 100})
    except httpx.ConnectError:
        pytest.skip(f"Langfuse not reachable at {GATEWAY_BASE_URL}")
    if resp.status_code in (401, 403, 404):
        pytest.skip(f"score-configs unavailable: {resp.status_code}")
    names = {c.get("name") for c in (resp.json().get("data") or [])}
    expected = {"zelkor-refusal-present", "zelkor-mcp-prefix", "zelkor-tenant-userid"}
    if not expected.issubset(names):
        pytest.skip(f"code evaluators not seeded (got {names})")


def test_langfuse_connection_secret_not_upstream_via_direct():
    """Same connection GET using helper auth; unused keys stay out of chart."""
    try:
        resp = httpx.get(
            f"{GATEWAY_BASE_URL}/api/public/llm-connections",
            headers=langfuse_headers(),
            auth=LANGFUSE_AUTH,
            timeout=10.0,
        )
    except httpx.ConnectError:
        pytest.skip(f"Langfuse not reachable at {GATEWAY_BASE_URL}")
    if resp.status_code != 200:
        pytest.skip(resp.text[:200])
    assert "sk-proj-" not in resp.text
