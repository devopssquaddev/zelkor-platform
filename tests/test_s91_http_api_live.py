"""S-91 / CE-21 acceptance 4 (live): a DNS-locked runtime agent calls an HTTP API through its gateway
route. The agent cannot resolve the API's host itself; an allowed call returns 200 with the
credential the gateway injected; a path outside the rules gets 403; the credential is never in
the agent's environment.

The sidecar relays /run/active/api/<name>/* only during a run, so the test holds one open (a
sandbox call that sleeps) and calls the API from the runtime container meanwhile. Lab fixture:
an httpApis entry (env ZELKOR_HTTP_API, default "echo") whose upstream echoes request headers
(https://httpbin.org; Cloudflare-fronted echo services reject non-browser clients),
rules Allow GET /get only, and a credential whose value is ZELKOR_HTTP_API_CANARY."""
from __future__ import annotations

import json
import os
import threading
import time

import pytest

from tests.helpers.runtime_agents import client, exec_python, runtime_graphs, tenant_token

API = os.environ.get("ZELKOR_HTTP_API", "echo").strip()
CANARY = os.environ.get("ZELKOR_HTTP_API_CANARY", "").strip()
UPSTREAM_HOST = os.environ.get("ZELKOR_HTTP_API_UPSTREAM_HOST", "httpbin.org").strip()

PROBE = """
import json, os, socket, urllib.error, urllib.request
API, CANARY, HOST = %r, %r, %r
url = os.environ["ZELKOR_API_%%s_URL" %% API.upper().replace("-", "_")].rstrip("/")
out = {}
try:
    socket.getaddrinfo(HOST, 443)
    out["dns"] = "resolved"
except Exception as exc:
    out["dns"] = type(exc).__name__
def get(path):
    try:
        r = urllib.request.urlopen(urllib.request.Request(url + path, headers={"user-agent": "zelkor-s91-probe/1"}), timeout=30)
        return [r.status, r.read().decode("utf-8", "replace")]
    except urllib.error.HTTPError as exc:
        return [exc.code, ""]
    except Exception as exc:
        return [type(exc).__name__, ""]
out["allowed"] = get("/get?s91=1")
out["denied"] = get("/status/200")
out["env_has_canary"] = any(CANARY in v for v in os.environ.values())
print("S91 " + json.dumps(out))
"""


@pytest.fixture(scope="module")
def probe() -> dict:
    if not CANARY:
        pytest.skip("ZELKOR_HTTP_API_CANARY not set (no HTTP API fixture on this lab)")
    graph = runtime_graphs()[0]
    token = tenant_token("tenant-a")
    done: dict = {}

    def hold_run():  # keeps the run active while the probe calls the API
        c = client(graph, token)
        thread = c.threads.create()["thread_id"]
        try:
            done["out"] = c.runs.wait(thread, graph, input={"messages": [{"role": "human", "content":
                "Call sandbox__execute_python once with timeout 60 and code: import time; time.sleep(45); print(1)"}]})
        except Exception as exc:  # noqa: BLE001 — the probe result is what counts
            done["error"] = exc

    t = threading.Thread(target=hold_run, daemon=True)
    t.start()
    time.sleep(15)  # the model has issued the tool call; the run is active
    line = next((l for l in exec_python(graph, "agent", PROBE % (API, CANARY, UPSTREAM_HOST)).splitlines()
                 if l.startswith("S91 ")), "")
    t.join(timeout=180)
    assert line, "probe printed nothing"
    return json.loads(line[4:])


def test_s91_agent_cannot_resolve_the_api_host(probe):
    assert probe["dns"] != "resolved", f"{UPSTREAM_HOST} resolved inside a DNS-locked agent"


def test_s91_allowed_call_goes_through_the_gateway_with_the_injected_credential(probe):
    status, body = probe["allowed"]
    assert status == 200, f"allowed call: {status} (no active run? route missing from the host map?)"
    assert CANARY in body, "the upstream did not receive the credential the gateway should inject"


def test_s91_call_outside_the_rules_is_403(probe):
    assert probe["denied"][0] == 403, probe["denied"]


def test_s91_credential_is_not_in_the_agent_env(probe):
    assert probe["env_has_canary"] is False
