"""S-75: what a runtime container can reach on its own (live; needs KUBECONTEXT, NetworkPolicies on).

NetworkPolicy is per pod and the sidecar in the same pod needs Postgres, Valkey and the AI
Gateway, so the runtime is held by credentials, not by the network, for those. Since 2.4.1 the
AI Gateway refuses callers without the consumer key (which only the sidecar holds) and NeMo is
reachable from Envoy only.
"""
from __future__ import annotations

import json
import os

import pytest

from tests.helpers.runtime_agents import exec_python, require_kube, runtime_graphs

REL = os.environ.get("ZELKOR_PLATFORM_RELEASE", "zelkor-platform")

PROBE = """
import json, os, socket, urllib.request, urllib.error
REL = %r
def tcp(host, port):
    try:
        socket.create_connection((host, port), timeout=4).close(); return "open"
    except Exception as e:
        return type(e).__name__
def post(url, body, headers=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
        headers={"content-type": "application/json", "accept": "application/json, text/event-stream", **(headers or {})})
    try:
        return urllib.request.urlopen(req, timeout=20).status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as e:
        return type(e).__name__
init = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "s75", "version": "1"}}}
chat = {"model": os.environ.get("DEFAULT_LLM_MODEL", "gpt-oss:20b"), "messages": [{"role": "user", "content": "say ok"}], "max_tokens": 5}
print(json.dumps({
  "env": sorted(k for k in os.environ if k in ("DATABASE_URL", "REDIS_URL", "VALKEY_URL", "OPENAI_ADMIN_KEY", "ANTHROPIC_API_KEY")),
  "openai_key": os.environ.get("OPENAI_API_KEY", ""),
  "qdrant": tcp(REL + "-qdrant", 6333),
  "worker": tcp(REL + "-mcp-sandbox-worker-0", 8081),
  "public": tcp("1.1.1.1", 443),
  "mcp_no_jwt": post("http://" + REL + "-mcp/mcp", init),
  "ai_gateway_no_key": post("http://" + REL + "-ai-gateway/v1/chat/completions", chat),
  "nemo_direct": post("http://" + REL + "-nemo:8000/v1/chat/completions", chat),
}))
"""


def _probe(graph: str) -> dict:
    return json.loads(exec_python(graph, "agent", PROBE % REL).strip().splitlines()[-1])


@pytest.fixture(scope="module")
def probes() -> dict[str, dict]:
    require_kube()
    return {g: _probe(g) for g in runtime_graphs()}


def test_s75_runtime_holds_no_credentials_and_no_open_egress(probes):
    for graph, p in probes.items():
        assert p["env"] == [], (graph, p["env"])
        assert p["openai_key"] in ("", "via-sidecar"), graph  # never a real consumer or provider key
        for target in ("qdrant", "worker", "public"):
            assert p[target] != "open", (graph, target, p[target])
        assert p["mcp_no_jwt"] == 401, (graph, p["mcp_no_jwt"])


def test_s75_runtime_cannot_call_models_without_the_sidecar(probes):
    for graph, p in probes.items():
        assert p["ai_gateway_no_key"] == 401, (graph, p["ai_gateway_no_key"])
        assert isinstance(p["nemo_direct"], str), (graph, p["nemo_direct"])  # connection refused / timeout
