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


def _is_public_https_host(host: str, scheme: str) -> bool:
    if scheme != "https" or not host or "." not in host:
        return False
    lowered = host.lower()
    return not lowered.endswith(".svc.cluster.local") and not lowered.endswith(".svc")


def extra_backend_overlay_snippet(name: str, url: str) -> str:
    parsed = urlparse((url or "").strip())
    host = (parsed.hostname or "").strip()
    scheme = (parsed.scheme or "").strip().lower()
    port = parsed.port or (443 if scheme == "https" else 80)
    path = parsed.path.strip() or "/mcp"
    lines = [
        "workspace:",
        "  tools:",
        "    extraBackends:",
        f"      - name: {name}",
    ]
    if _is_public_https_host(host, scheme):
        lines.append("        fqdn:")
        lines.append(f"          hostname: {host}")
        lines.append(f"          port: {port}")
        lines.append(f"        path: {path}")
    elif host:
        svc = host.split(".")[0]
        lines.append("        service:")
        lines.append(f"          name: {svc}")
        lines.append(f"          port: {port}")
        if path and path != "/":
            lines.append(f"        path: {path}")
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
