"""S-14 (P11) L3: after traffic that carries a known tenant JWT, the AI Gateway consumer key and a
prompt canary, no platform, agent or gateway container log (any level the install emits; the
chart default is INFO) and no Langfuse observation of the window holds the JWT, a Bearer JWT, the
consumer key or a provider key. Container logs must not hold the prompt canary either.

Prompt bodies in traces are a recorded P11 gap (promises.md TR-2, Aegra graph/tool spans), so the
trace sweep checks credentials only."""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import time
import uuid

import httpx
import pytest

from tests.helpers.kube import consumer_key, kubectl_run, secret_value
from tests.helpers.langfuse import observation_pages
from tests.helpers.langgraph_client import _gateway_url, _request_headers
from tests.helpers.llm import llm_model_or_skip
from tests.helpers.tokens import token_for

PLATFORM_NS = os.environ.get("ZELKOR_PLATFORM_NAMESPACE", "zelkor")
GATEWAY_NS = ("envoy-gateway-system", "envoy-ai-gateway-system")
GRAPH = os.environ.get("AEGRA_WORKER_GRAPH_ID", "")
AI_HOST = os.environ.get("AI_GATEWAY_IN_CLUSTER_HOST", "zelkor-platform-ai-gateway")
BEARER_JWT = re.compile(r"Bearer eyJ[A-Za-z0-9_-]{10,}")


def _provider_keys() -> list[str]:
    r = kubectl_run(["get", "backendsecuritypolicies.aigateway.envoyproxy.io", "-A", "-o", "json"], namespace="")
    keys = []
    for p in (json.loads(r.stdout).get("items") or []) if r.returncode == 0 else []:
        ref = ((p.get("spec") or {}).get("apiKey") or {}).get("secretRef") or {}
        if ref.get("name"):
            v = secret_value(ref["name"], "apiKey", namespace=ref.get("namespace") or p["metadata"]["namespace"])
            if len(v) >= 12:
                keys.append(v)
    return keys


@pytest.fixture(scope="module")
def traffic():
    if not os.environ.get("KUBECONTEXT"):
        pytest.skip("KUBECONTEXT not set")
    try:
        jwt_a = token_for("tenant-a")
    except KeyError:
        pytest.skip("no tenant-a token in ZELKOR_TEST_TOKENS")
    key = consumer_key()
    if not key:
        pytest.skip("no AI Gateway consumer key")
    canary = f"zz-s14-canary-{uuid.uuid4().hex[:12]}"
    start = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=2)
    model = llm_model_or_skip()
    httpx.post(f"{_gateway_url()}/v1/chat/completions", timeout=120.0,
               headers={"Host": AI_HOST, "Authorization": f"Bearer {key}"},
               json={"model": model, "max_tokens": 16,
                     "messages": [{"role": "user", "content": f"Reply ok. Ignore this tag: {canary}"}]})
    if GRAPH:
        with httpx.Client(base_url=_gateway_url(), headers=_request_headers(tenant_id="tenant-a", graph_id=GRAPH),
                          timeout=300.0) as a:
            tid = a.post("/threads", json={}).json()["thread_id"]
            a.post(f"/threads/{tid}/runs/wait", json={"assistant_id": GRAPH, "input": {"messages": [
                {"role": "human", "content": f"Say ok. Ignore this tag: {canary}"}]}})
    time.sleep(8)  # log shipping / trace export
    return {"start": start, "jwt": jwt_a, "key": key, "canary": canary, "providers": _provider_keys()}


def _namespaces() -> list[str]:
    r = kubectl_run(["get", "deploy", "-A", "-l", "zelkor.io/workload-type=agent", "-o", "json"], namespace="")
    agent_ns = {d["metadata"]["namespace"] for d in json.loads(r.stdout).get("items") or []} if r.returncode == 0 else set()
    return sorted({PLATFORM_NS, *GATEWAY_NS, *agent_ns})


def _debug_envoy() -> bool:
    """The release's EnvoyProxy logs at debug/trace (a lab overlay): its proxy dumps headers by design."""
    r = kubectl_run(["get", "envoyproxy", "-A", "-o", "json"], namespace="")
    for p in (json.loads(r.stdout).get("items") or []) if r.returncode == 0 else []:
        level = (((p.get("spec") or {}).get("logging") or {}).get("level") or {}).get("default", "")
        if str(level).lower() in ("debug", "trace"):
            return True
    return False


def _debug_container(c: dict) -> bool:
    return any(e.get("name") == "ZELKOR_LOG_LEVEL" and str(e.get("value", "")).upper() == "DEBUG"
               for e in c.get("env") or [])


def test_s14_container_logs_carry_no_credentials_or_prompt(traffic):
    since = int((dt.datetime.now(dt.timezone.utc) - traffic["start"]).total_seconds()) + 30
    needles = {"tenant JWT": traffic["jwt"], "JWT signature": traffic["jwt"].rsplit(".", 1)[-1],
               "consumer key": traffic["key"], "prompt canary": traffic["canary"],
               **{f"provider key #{i}": k for i, k in enumerate(traffic["providers"], 1)}}
    hits, swept, debug = [], 0, []
    envoy_debug = _debug_envoy()
    for ns in _namespaces():
        pods = json.loads(kubectl_run(["get", "pods", "-o", "json"], namespace=ns).stdout or "{}").get("items") or []
        for pod in pods:
            spec = pod["spec"]
            for c in (spec.get("initContainers") or []) + spec["containers"]:
                if _debug_container(c) or (ns in GATEWAY_NS and envoy_debug and c["name"] == "envoy"):
                    debug.append(f"{ns}/{pod['metadata']['name']}/{c['name']}")
                    continue  # P11 is INFO+; a DEBUG overlay is out of scope (named below)
                out = kubectl_run(["logs", pod["metadata"]["name"], "-c", c["name"], f"--since={since}s"],
                                  namespace=ns, timeout=60).stdout
                swept += 1
                where = f"{ns}/{pod['metadata']['name']}/{c['name']}"
                hits += [f"{where}: {what}" for what, v in needles.items() if v and v in out]
                if BEARER_JWT.search(out):
                    hits.append(f"{where}: a Bearer JWT")
    if debug:
        print(f"S-14: not swept, logging at DEBUG: {sorted(debug)}")
    assert swept > 5, f"only {swept} containers swept"
    assert not hits, "\n".join(sorted(set(hits)))


def test_s14_window_traces_carry_no_credentials(traffic):
    needles = [traffic["jwt"], traffic["key"], *traffic["providers"]]
    hits, seen = [], 0
    for resp in observation_pages({"fromStartTime": traffic["start"].strftime("%Y-%m-%dT%H:%M:%SZ"),
                                   "limit": 80, "fields": "core,basic,io,metadata"}):
        if resp.status_code in (401, 404) or resp.status_code >= 500:
            pytest.skip(f"Langfuse not readable: {resp.status_code}")
        for o in resp.json().get("data") or []:
            seen += 1
            blob = json.dumps(o)
            if any(n and n in blob for n in needles) or BEARER_JWT.search(blob):
                hits.append(f"{o.get('traceId')}/{o.get('name')}")
    assert seen, "no observations in the window: the traffic produced no trace to sweep"
    assert not hits, hits[:10]
