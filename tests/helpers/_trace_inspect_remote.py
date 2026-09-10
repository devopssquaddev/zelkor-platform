#!/usr/bin/env python3
"""One-off remote trace inspection (test server)."""
import json
import sys

import httpx

G = "http://127.0.0.1:8088"
auth = ("pk-lf-zelkor-dev-00000000000000000000", "sk-lf-zelkor-dev-00000000000000000000")
h = {"Host": "langfuse.localhost"}
tid = sys.argv[1] if len(sys.argv) > 1 else "451760b0e5d72b30912bbb3c6ed02edf"
d = httpx.get(f"{G}/api/public/traces/{tid}", headers=h, auth=auth, timeout=15).json()
obs = d.get("observations") or []
if not obs:
    obs = httpx.get(
        f"{G}/api/public/observations",
        headers=h,
        auth=auth,
        params={"traceId": tid, "limit": 100},
        timeout=15,
    ).json().get("data", [])
print(json.dumps({"name": d.get("name"), "userId": d.get("userId"), "sessionId": d.get("sessionId"), "metadata": d.get("metadata")}, indent=2))
print(f"observations={len(obs)}")
for o in obs:
    print(
        f"{o.get('name')} | {o.get('type')} | parent={o.get('parentObservationId')} "
        f"| in={bool(o.get('input'))} out={bool(o.get('output'))}"
    )
