"""Extra MCP backend configuration (compiled from workspace.tools.extraBackends)."""
from __future__ import annotations

import base64
import json
import os
import re
import ssl
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple

_DNS_LABEL = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")
RESERVED_PREFIXES = frozenset({"postgres", "qdrant", "sandbox", "egress", "nemo", "aegra", "langfuse"})


@dataclass
class BackendConfig:
    name: str
    url: str
    path: str = "/mcp"
    timeout_seconds: int = 30
    forward_authorization: bool = True
    forward_tenant_header: bool = True
    inject_tenant_arg: bool = True
    static_headers: Dict[str, str] = field(default_factory=dict)
    headers_from_env: Dict[str, str] = field(default_factory=dict)
    auth_type: str = "none"
    auth_bearer_env: str = ""
    auth_header_name: str = ""
    auth_header_env: str = ""
    auth_basic_user_env: str = ""
    auth_basic_pass_env: str = ""
    tls_ca_path: str = ""
    tls_ca_env: str = ""

    @property
    def rpc_url(self) -> str:
        base = self.url.rstrip("/")
        path = self.path if self.path.startswith("/") else f"/{self.path}"
        if base.endswith(path):
            return base
        return f"{base}{path}"


def validate_extra_name(name: str) -> str:
    if not name or not isinstance(name, str):
        raise ValueError("extra backend name is required")
    if "__" in name:
        raise ValueError("extra backend name must not contain __")
    if name in RESERVED_PREFIXES:
        raise ValueError(f"extra backend name collides with reserved prefix: {name}")
    if not _DNS_LABEL.match(name):
        raise ValueError(f"extra backend name must be a DNS label: {name}")
    return name


def _bool(item: Mapping[str, Any], key: str, default: bool) -> bool:
    if key not in item:
        return default
    val = item[key]
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.strip().lower() in ("1", "true", "yes", "on")
    return bool(val)


def parse_extra_backend_item(item: Mapping[str, Any]) -> BackendConfig:
    if not isinstance(item, dict):
        raise ValueError("extra backend entries must be objects with name and url")
    name = validate_extra_name((item.get("name") or "").strip())
    url = (item.get("url") or "").strip()
    if not url:
        raise ValueError(f"extra backend {name} is missing url")

    auth = item.get("auth") or {}
    if not isinstance(auth, dict):
        auth = {}
    auth_type = (auth.get("type") or "none").strip().lower()
    if auth_type not in ("none", "bearer", "basic", "header"):
        raise ValueError(f"extra backend {name}: auth.type must be none, bearer, basic, or header")

    forward_auth = _bool(item, "forwardAuthorization", True)
    if auth_type in ("bearer", "basic", "header"):
        forward_auth = False

    static_headers: Dict[str, str] = {}
    raw_headers = item.get("headers") or {}
    if isinstance(raw_headers, dict):
        for k, v in raw_headers.items():
            if k and v is not None:
                static_headers[str(k)] = str(v)

    headers_from_env: Dict[str, str] = {}
    for entry in item.get("headersFrom") or []:
        if not isinstance(entry, dict):
            continue
        header = (entry.get("header") or "").strip()
        env_name = (entry.get("env") or "").strip()
        if header and env_name:
            headers_from_env[header] = env_name

    tls = item.get("tls") or {}
    if not isinstance(tls, dict):
        tls = {}

    timeout = item.get("timeoutSeconds", 30)
    try:
        timeout_seconds = int(timeout)
    except (TypeError, ValueError):
        timeout_seconds = 30
    if timeout_seconds <= 0:
        timeout_seconds = 30

    return BackendConfig(
        name=name,
        url=url,
        path=(item.get("path") or "/mcp").strip() or "/mcp",
        timeout_seconds=timeout_seconds,
        forward_authorization=forward_auth,
        forward_tenant_header=_bool(item, "forwardTenantHeader", True),
        inject_tenant_arg=_bool(item, "injectTenantArg", True),
        static_headers=static_headers,
        headers_from_env=headers_from_env,
        auth_type=auth_type,
        auth_bearer_env=(auth.get("bearerEnv") or auth.get("env") or "").strip(),
        auth_header_name=(auth.get("headerName") or "").strip(),
        auth_header_env=(auth.get("headerEnv") or auth.get("env") or "").strip(),
        auth_basic_user_env=(auth.get("usernameEnv") or "").strip(),
        auth_basic_pass_env=(auth.get("passwordEnv") or "").strip(),
        tls_ca_path=(tls.get("caPath") or "").strip(),
        tls_ca_env=(tls.get("caEnv") or "").strip(),
    )


def parse_extra_backends(raw: str) -> List[BackendConfig]:
    text = (raw or "").strip()
    if not text:
        return []
    data = json.loads(text)
    if data is None:
        return []
    if not isinstance(data, list):
        raise ValueError("MCP_EXTRA_BACKENDS must be a JSON list of backend objects")
    return [parse_extra_backend_item(item) for item in data]


def merge_backends(
    native: Dict[str, str],
    extra: List[BackendConfig],
) -> Dict[str, BackendConfig]:
    merged: Dict[str, BackendConfig] = {
        k: BackendConfig(name=k, url=v) for k, v in native.items()
    }
    for cfg in extra:
        if cfg.name in merged:
            raise ValueError(f"extra backend name already in use: {cfg.name}")
        merged[cfg.name] = cfg
    return merged


def _env_value(env_name: str) -> str:
    if not env_name:
        return ""
    return os.getenv(env_name, "").strip()


def build_outbound_headers(
    cfg: BackendConfig,
    inbound: Mapping[str, str],
) -> Dict[str, str]:
    hdrs: Dict[str, str] = {"Content-Type": "application/json"}
    hdrs.update(cfg.static_headers)
    for header, env_name in cfg.headers_from_env.items():
        val = _env_value(env_name)
        if val:
            hdrs[header] = val

    if cfg.auth_type == "bearer":
        token = _env_value(cfg.auth_bearer_env)
        if token:
            hdrs["Authorization"] = token if token.lower().startswith("bearer ") else f"Bearer {token}"
    elif cfg.auth_type == "header":
        val = _env_value(cfg.auth_header_env)
        if val and cfg.auth_header_name:
            hdrs[cfg.auth_header_name] = val
    elif cfg.auth_type == "basic":
        user = _env_value(cfg.auth_basic_user_env)
        password = _env_value(cfg.auth_basic_pass_env)
        if user or password:
            raw = f"{user}:{password}".encode("utf-8")
            hdrs["Authorization"] = "Basic " + base64.b64encode(raw).decode("ascii")

    if cfg.forward_authorization:
        for k, v in inbound.items():
            if k.lower() == "authorization" and v:
                hdrs["Authorization"] = v
                break
    if cfg.forward_tenant_header:
        for k, v in inbound.items():
            if k.lower() == "x-tenant-id" and v:
                hdrs["X-Tenant-ID"] = v
                break
    return hdrs


def ssl_context_for(cfg: BackendConfig) -> Optional[ssl.SSLContext]:
    ca_pem = ""
    if cfg.tls_ca_path and os.path.isfile(cfg.tls_ca_path):
        with open(cfg.tls_ca_path, "rb") as fh:
            ca_pem = fh.read().decode("utf-8", errors="replace")
    elif cfg.tls_ca_env:
        ca_pem = _env_value(cfg.tls_ca_env)
    if not ca_pem:
        return None
    ctx = ssl.create_default_context()
    ctx.load_verify_locations(cadata=ca_pem)
    return ctx


def rpc_call(cfg: BackendConfig, method: str, params: dict, inbound_headers: Mapping[str, str]) -> Any:
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode("utf-8")
    hdrs = build_outbound_headers(cfg, inbound_headers)
    ctx = ssl_context_for(cfg)
    req = urllib.request.Request(cfg.rpc_url, data=payload, headers=hdrs, method="POST")
    open_kw: Dict[str, Any] = {"timeout": cfg.timeout_seconds}
    if ctx is not None:
        open_kw["context"] = ctx
    with urllib.request.urlopen(req, **open_kw) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        if "error" in data:
            raise RuntimeError(data["error"].get("message", str(data["error"])))
        return data.get("result")
