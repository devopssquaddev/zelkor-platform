"""BYO MCP extras: compare tools.json with platform Helm values (no platform mutation)."""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse


def extra_backends_from_values(values: dict[str, Any]) -> list[dict[str, Any]]:
    tools = values.get("workspace", {}).get("tools") if isinstance(values.get("workspace"), dict) else {}
    if not isinstance(tools, dict):
        tools = {}
    mcp = values.get("mcp") if isinstance(values.get("mcp"), dict) else {}
    rows = mcp.get("extraBackends") or tools.get("extraBackends") or []
    return [r for r in rows if isinstance(r, dict)]


def registered_extra_names(values: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for row in extra_backends_from_values(values):
        name = str(row.get("name") or "").strip()
        if name:
            names.add(name)
    return names


def _service_hint_from_url(url: str) -> tuple[str, int]:
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").strip()
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if not host:
        return "", 0
    svc = host.split(".")[0] if host else ""
    return svc, port


def extra_backend_overlay_snippet(name: str, url: str) -> str:
    svc, port = _service_hint_from_url(url)
    lines = [
        "workspace:",
        "  tools:",
        "    extraBackends:",
        f"      - name: {name}",
    ]
    if svc:
        lines.append("        service:")
        lines.append(f"          name: {svc}")
        lines.append(f"          port: {port}")
    else:
        lines.append(f"        # register upstream for {url!r} (service or fqdn required)")
    lines.append("        apiKey:")
    lines.append("          secretRef:")
    lines.append(f"            name: {re.sub(r'[^a-z0-9-]', '-', name.lower())}-mcp-key")
    return "\n".join(lines)


def missing_extra_registrations(
    servers: tuple[dict[str, str], ...] | list[dict[str, str]],
    values: dict[str, Any],
) -> list[dict[str, str]]:
    registered = registered_extra_names(values)
    missing: list[dict[str, str]] = []
    for row in servers:
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        if name not in registered:
            missing.append({"name": name, "url": str(row.get("url") or "")})
    return missing


def format_missing_extras_error(missing: list[dict[str, str]]) -> str:
    parts = [
        "tools.json lists MCP servers that are not registered on the platform release.",
        "zelkor deploy does not mutate the platform chart; add extras in your GitOps overlay "
        "(see docs/mcp-extra-backends.md), then redeploy the platform.",
    ]
    for row in missing:
        parts.append("")
        parts.append(f"Missing extra backend: {row['name']}")
        parts.append(extra_backend_overlay_snippet(row["name"], row.get("url", "")))
    return "\n".join(parts)
