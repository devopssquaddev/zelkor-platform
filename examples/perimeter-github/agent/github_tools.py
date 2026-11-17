"""GitHub tools for the repo-triage agent. They hold no token: they call the Zelkor relay at
$ZELKOR_API_GITHUB_URL (the sidecar loopback), and the gateway adds the token and decides which
methods and paths are allowed. A denied call comes back as text the model can explain."""
from __future__ import annotations

import json
import os
from typing import Any, Optional

import httpx

MAX_CHARS = 6000
ISSUE_FIELDS = ("number", "title", "state", "created_at", "html_url")
_transport: Optional[httpx.AsyncBaseTransport] = None  # tests swap in a mock


def _slim(data: Any) -> Any:
    """Issue lists keep what triage needs; GitHub's full objects are mostly noise to the model."""
    items = data.get("items") if isinstance(data, dict) and "items" in data else data
    if isinstance(items, list) and items and all(isinstance(i, dict) and "number" in i for i in items):
        return [{**{k: i.get(k) for k in ISSUE_FIELDS},
                 "labels": [label.get("name") for label in i.get("labels") or []]} for i in items]
    return data


async def _call(method: str, path: str, body: Optional[dict] = None) -> str:
    base = os.environ.get("ZELKOR_API_GITHUB_URL", "").rstrip("/")
    if not base:
        return "error: ZELKOR_API_GITHUB_URL is not set (the platform has no `github` HTTP API)"
    async with httpx.AsyncClient(transport=_transport, timeout=30.0) as client:
        resp = await client.request(method, f"{base}/{path.lstrip('/')}", json=body,
                                    headers={"Accept": "application/vnd.github+json"})
    if resp.status_code == 403:
        return f"HTTP 403: {method} {path} is not permitted by the gateway policy."
    if resp.status_code >= 400:
        return f"HTTP {resp.status_code}: {resp.text[:500]}"
    try:
        text = json.dumps(_slim(resp.json()))
    except ValueError:
        text = resp.text
    return text[:MAX_CHARS]


async def github_read(path: str) -> str:
    """GET a GitHub REST API path, for example
    /repos/octocat/Hello-World/issues?state=open&sort=created&direction=asc&per_page=10"""
    return await _call("GET", path)


async def github_write(method: str, path: str, body: Optional[dict] = None) -> str:
    """Change something on GitHub with PATCH, POST, PUT or DELETE, for example
    PATCH /repos/octocat/Hello-World/issues/1 with body {"state": "closed"}."""
    return await _call(method.upper(), path, body)
