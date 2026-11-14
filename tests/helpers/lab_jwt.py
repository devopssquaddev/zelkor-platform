"""Sign tenant JWTs with arbitrary claims on a lab install (live tests only).

`zelkor token mint` signs `tenant_id` only. Identity tests also need tokens with other claim sets
(e.g. `sub` only), so this signs like the mint does: the release's `{release}-tenant-jwt-signing`
Secret and the issuer / audiences from its tenant-JWT ConfigMap. Skips when unavailable.
"""
from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timedelta, timezone

import pytest

from tests.helpers.kube import kubectl_run, platform_contract


def sign(claims: dict, *, ttl_minutes: int = 30) -> str:
    import jwt

    ns = os.environ.get("ZELKOR_PLATFORM_NAMESPACE", "zelkor")
    release = os.environ.get("ZELKOR_PLATFORM_RELEASE", "zelkor-platform")
    sec = kubectl_run(["get", "secret", f"{release}-tenant-jwt-signing", "-o", "jsonpath={.data}"], namespace=ns)
    if sec.returncode != 0 or not sec.stdout.strip():
        pytest.skip(f"no {release}-tenant-jwt-signing Secret (lab signing only)")
    data = {k: base64.b64decode(v).decode() for k, v in json.loads(sec.stdout).items()}
    cm_name = platform_contract(ns).get("TENANT_JWT_CONFIGMAP", f"{release}-tenant-jwt")
    cm = kubectl_run(["get", "configmap", cm_name, "-o", "jsonpath={.data}"], namespace=ns)
    jwt_cfg = json.loads(cm.stdout) if cm.returncode == 0 and cm.stdout.strip() else {}
    issuer = jwt_cfg.get("AUTH_JWT_ISSUER", "")
    audiences = [a.strip() for a in jwt_cfg.get("AUTH_JWT_AUDIENCES", "").replace("[", "").replace("]", "")
                 .replace('"', "").split(",") if a.strip()]
    if not issuer:
        pytest.skip("tenant-JWT ConfigMap has no AUTH_JWT_ISSUER")
    now = datetime.now(timezone.utc)
    payload = {"iss": issuer, "aud": audiences, "iat": now, "exp": now + timedelta(minutes=ttl_minutes), **claims}
    return jwt.encode(payload, data["privateKey"].encode(), algorithm="RS256", headers={"kid": data.get("kid", "1")})
