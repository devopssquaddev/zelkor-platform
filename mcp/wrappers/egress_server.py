"""Zelkor egress MCP — AI Gateway /v1 only (CE-3).

call_external_api POSTs chat.completions or embeddings to AI_GATEWAY_URL.
Rejects model-supplied url / base_url / Authorization.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.mcp_server import MCPToolHandler, run_mcp_server
from common.tenant import extract_tenant

logger = logging.getLogger("zelkor-egress-mcp")

AI_GATEWAY_URL = os.getenv("AI_GATEWAY_URL", "").rstrip("/")
AI_GATEWAY_API_KEY = os.getenv("AI_GATEWAY_API_KEY", "")
ALLOWED_MODELS = [m.strip() for m in os.getenv("EGRESS_ALLOWED_MODELS", "").split(",") if m.strip()]

_FORBIDDEN_ARG_KEYS = frozenset({"url", "base_url", "baseurl", "authorization", "api_key", "apikey"})


def parse_allowed_models(raw: str) -> List[str]:
    return [m.strip() for m in (raw or "").split(",") if m.strip()]


def reject_forbidden_args(arguments: dict) -> None:
    for key in arguments:
        if str(key).lower() in _FORBIDDEN_ARG_KEYS:
            raise PermissionError(f"call_external_api rejects {key}")


def gateway_path(operation: str) -> str:
    op = (operation or "chat.completions").strip().lower()
    if op in ("chat.completions", "chat", "chat/completions"):
        return "chat/completions"
    if op in ("embeddings", "embedding"):
        return "embeddings"
    raise ValueError(f"unsupported operation: {operation}")


def build_body(operation: str, arguments: dict, model: str) -> dict:
    path = gateway_path(operation)
    if path == "embeddings":
        text = arguments.get("input")
        if text is None:
            raise ValueError("input is required for embeddings")
        return {"model": model, "input": text}
    messages = arguments.get("messages")
    if not messages:
        raise ValueError("messages is required for chat.completions")
    return {"model": model, "messages": messages}


def post_gateway(path: str, body: dict) -> dict:
    if not AI_GATEWAY_URL:
        raise RuntimeError("AI_GATEWAY_URL is not set")
    url = f"{AI_GATEWAY_URL.rstrip('/')}/{path.lstrip('/')}"
    headers = {"Content-Type": "application/json"}
    if AI_GATEWAY_API_KEY:
        headers["Authorization"] = f"Bearer {AI_GATEWAY_API_KEY}"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"AI Gateway {exc.code}: {detail}") from exc


class EgressMCPServer(MCPToolHandler):
    def __init__(self, allowed_models: Optional[List[str]] = None):
        self.allowed_models = allowed_models if allowed_models is not None else ALLOWED_MODELS

    def list_tools(self):
        return [
            {
                "name": "call_external_api",
                "description": (
                    "Call the in-cluster Envoy AI Gateway /v1 "
                    "(chat.completions or embeddings). "
                    "Do not pass url, base_url, or Authorization."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "tenant_id": {"type": "string"},
                        "model": {"type": "string"},
                        "operation": {"type": "string"},
                        "messages": {"type": "array"},
                        "input": {},
                    },
                    "required": ["tenant_id", "model"],
                },
            }
        ]

    def call_tool(self, name: str, arguments: dict, tenant_id: str) -> Any:
        if name != "call_external_api":
            raise ValueError(f"Unknown tool: {name}")
        reject_forbidden_args(arguments)
        arg_tenant = arguments.get("tenant_id")
        if not arg_tenant or arg_tenant != tenant_id:
            raise PermissionError(f"tenant_id mismatch: header={tenant_id}, arg={arg_tenant}")
        model = (arguments.get("model") or "").strip()
        if not model:
            raise ValueError("model is required")
        if self.allowed_models and model not in self.allowed_models:
            raise PermissionError(f"model not allowed: {model}")
        operation = arguments.get("operation") or "chat.completions"
        path = gateway_path(operation)
        body = build_body(operation, arguments, model)
        return post_gateway(path, body)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_mcp_server(EgressMCPServer(), extract_tenant, port=int(os.getenv("PORT", "8080")))
