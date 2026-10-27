"""UAT-26 / S-77 / S-79: the runtime container itself cannot widen its tools or act outside a run (live).

Calls go from inside the ``agent`` container to the sidecar loopback, the same position a
compromised runtime would have. Needs KUBECONTEXT. The agent must be deployed with a tool scope
that excludes ``ZELKOR_OUT_OF_SCOPE_TOOL`` (default ``qdrant__search_documents``; deploy with
``--tools postgres,sandbox``).
"""
from __future__ import annotations

import json
import os
import threading
import time

from tests.helpers.runtime_agents import (
    container_logs, deployment, exec_python, require_kube, run, runtime_graphs, tenant_token,
)

PROBE = """
import json, urllib.request, urllib.error
req = urllib.request.Request("http://127.0.0.1:8001/run/active/mcp",
    data=json.dumps({"jsonrpc": "2.0", "id": 7, "method": "tools/call",
                     "params": {"name": %r, "arguments": {}}}).encode(),
    headers={"content-type": "application/json", "accept": "application/json, text/event-stream",
             "authorization": "Bearer forged-by-runtime"})
try:
    r = urllib.request.urlopen(req, timeout=20); print(json.dumps({"status": r.status, "body": r.read().decode()[:400]}))
except urllib.error.HTTPError as e:
    print(json.dumps({"status": e.code, "body": e.read().decode()[:400]}))
"""

LONG_RUN = ("Call sandbox__execute_python once with timeout 60 and code: "
            "import time; time.sleep(25); print(1)")


def _tool() -> str:
    return os.environ.get("ZELKOR_OUT_OF_SCOPE_TOOL", "qdrant__search_documents")


def _probe(graph: str) -> dict:
    return json.loads(exec_python(graph, "agent", PROBE % _tool()).strip().splitlines()[-1])


def test_uat26_no_active_run_is_refused_from_the_runtime():
    require_kube()
    for graph in runtime_graphs():
        assert _probe(graph)["status"] == 409, graph


def test_uat26_out_of_scope_tool_refused_during_a_run():
    require_kube()
    graph = runtime_graphs()[0]
    token = tenant_token("tenant-a")
    worker = threading.Thread(target=run, args=(graph, token, LONG_RUN), daemon=True)
    worker.start()
    result = {"status": 409}
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline and result["status"] == 409:
        time.sleep(2)
        result = _probe(graph)
    worker.join(timeout=120)
    assert result["status"] == 200, result
    body = json.loads(result["body"])
    assert "error" in body and "tool scope" in body["error"]["message"], body
    logs = container_logs(deployment(graph), "sidecar")
    assert "tool outside agent scope" in logs and _tool() in logs
