"""zelkor token mint / jwks — RS256 tokens from cluster signing secret."""
from __future__ import annotations

import base64
import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import jwt


def _resolve_context(args_context: str) -> str:
    if args_context:
        return args_context
    return os.environ.get("KUBE_CONTEXT", "") or os.environ.get("KUBECONTEXT", "")


def _kubectl_cmd(kubeconfig: str, context: str) -> list[str]:
    cmd = ["kubectl"]
    if kubeconfig:
        cmd.extend(["--kubeconfig", kubeconfig])
    if context:
        cmd.extend(["--context", context])
    return cmd


def _kube_get_secret(
    kubeconfig: str,
    context: str,
    namespace: str,
    name: str,
) -> dict[str, str]:
    cmd = _kubectl_cmd(kubeconfig, context)
    cmd.extend(["-n", namespace, "get", "secret", name, "-o", "json"])
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        raise RuntimeError(f"cannot read secret {name}: {res.stderr or res.stdout}")
    data = json.loads(res.stdout).get("data") or {}
    return {k: base64.b64decode(v).decode("utf-8", errors="replace") for k, v in data.items()}


def _kube_get_configmap(
    kubeconfig: str,
    context: str,
    namespace: str,
    name: str,
) -> dict[str, str]:
    obj = _kube_get_configmap_object(kubeconfig, context, namespace, name)
    return obj.get("data") or {}


def _kube_get_configmap_object(
    kubeconfig: str,
    context: str,
    namespace: str,
    name: str,
) -> dict[str, Any]:
    cmd = _kubectl_cmd(kubeconfig, context)
    cmd.extend(["-n", namespace, "get", "configmap", name, "-o", "json"])
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        raise RuntimeError(f"cannot read configmap {name}: {res.stderr or res.stdout}")
    return json.loads(res.stdout)


def _parse_audiences(raw: str) -> list[str]:
    raw = (raw or "").strip()
    if not raw:
        return ["zelkor"]
    if raw.startswith("["):
        parsed = json.loads(raw)
        return [str(a) for a in parsed]
    return [a.strip() for a in raw.split(",") if a.strip()]


def _parse_ttl(raw: str) -> timedelta:
    raw = (raw or "1h").strip()
    if raw.endswith("h"):
        return timedelta(hours=int(raw[:-1]))
    if raw.endswith("m"):
        return timedelta(minutes=int(raw[:-1]))
    if raw.endswith("d"):
        return timedelta(days=int(raw[:-1]))
    return timedelta(hours=1)


def cmd_token_mint(args: Any) -> int:
    release = args.release
    namespace = args.namespace or "default"
    kubeconfig = args.kubeconfig or os.environ.get("KUBECONFIG", "")
    context = _resolve_context(args.context or "")
    tenant = args.tenant
    signing = f"{release}-tenant-jwt-signing"
    jwks_cm = f"{release}-tenant-jwks"
    jwt_cm = f"{release}-tenant-jwt"
    sec = _kube_get_secret(kubeconfig, context, namespace, signing)
    priv_pem = sec.get("privateKey", "").encode()
    kid = sec.get("kid", "1")
    jwks_obj = _kube_get_configmap_object(kubeconfig, context, namespace, jwks_cm)
    jwt_data = _kube_get_configmap(kubeconfig, context, namespace, jwt_cm)
    annotations = (jwks_obj.get("metadata") or {}).get("annotations") or {}
    if args.ttl:
        ttl = _parse_ttl(args.ttl)
    else:
        ttl = _parse_ttl(annotations.get("zelkor.io/token-ttl", "1h"))
    issuer = args.issuer or os.environ.get("AUTH_JWT_ISSUER", "") or jwt_data.get("AUTH_JWT_ISSUER", "")
    audiences_raw = (
        args.audience
        or os.environ.get("AUTH_JWT_AUDIENCES", "")
        or jwt_data.get("AUTH_JWT_AUDIENCES", "")
    )
    aud = _parse_audiences(audiences_raw)
    if not issuer:
        raise SystemExit("set --issuer or AUTH_JWT_ISSUER (or deploy platform tenant-jwt ConfigMap)")
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "iss": issuer,
            "aud": aud,
            "tenant_id": tenant,
            "exp": now + ttl,
            "iat": now,
        },
        priv_pem,
        algorithm="RS256",
        headers={"kid": kid},
    )
    if args.out:
        Path(args.out).write_text(token + "\n", encoding="utf-8")
    else:
        print(token)
    return 0


def cmd_token_jwks(args: Any) -> int:
    release = args.release
    namespace = args.namespace or "default"
    kubeconfig = args.kubeconfig or os.environ.get("KUBECONFIG", "")
    context = _resolve_context(args.context or "")
    jwks_cm = f"{release}-tenant-jwks"
    cm = _kube_get_configmap(kubeconfig, context, namespace, jwks_cm)
    jwks = cm.get("jwks", "{}")
    out = Path(args.out)
    out.write_text(jwks if jwks.strip().startswith("{") else json.dumps(json.loads(jwks)), encoding="utf-8")
    if args.env_file:
        env_path = Path(args.env_file)
        lines = []
        if env_path.is_file():
            lines = env_path.read_text(encoding="utf-8").splitlines()
        lines = [ln for ln in lines if not ln.startswith("AUTH_JWKS_PATH=")]
        lines.append(f"AUTH_JWKS_PATH={out.resolve()}")
        env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0
