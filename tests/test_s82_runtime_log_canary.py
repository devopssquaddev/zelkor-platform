"""S-82 / UAT-17: prompt and tool-argument canaries never reach logs at INFO+ (live; needs KUBECONTEXT).

Covers the sidecar, the runtime container, NeMo and the native MCP servers. Also checks NeMo
keeps emitting Zelkor JSON after a request (its vendor verbose mode used to mute it and print
prompts as text).
"""
from __future__ import annotations

import json
import os
import uuid

from tests.helpers.kube import kubectl_run
from tests.helpers.runtime_agents import (
    container_logs, deployment, require_kube, run, runtime_graphs, tenant_token,
)

REL = os.environ.get("ZELKOR_PLATFORM_RELEASE", "zelkor-platform")


def _nemo_logs(since: str) -> str:
    proc = kubectl_run(["logs", "-l", "app.kubernetes.io/component=guardrails", "-c", "nemo-guardrails",
                        f"--since={since}", "--tail=-1", "--prefix"], timeout=90)
    return proc.stdout


def test_s82_canary_absent_from_logs_and_nemo_stays_json():
    require_kube()
    token = tenant_token("tenant-a")
    canary = f"ZLKCANARY{uuid.uuid4().hex[:16]}"
    graphs = runtime_graphs()
    for graph in graphs:
        prompt = (f"My reference is {canary}. Call sandbox__execute_python once with timeout 30 and code "
                  f"print('{canary}') then repeat the output.")
        run(graph, token, prompt)

    leaks = {}
    for graph in graphs:
        for container in ("sidecar", "agent"):
            if canary in container_logs(deployment(graph), container, since="10m"):
                leaks[f"{graph}/{container}"] = True
    for name in ("mcp-sandbox", "mcp-postgres"):
        if canary in container_logs(f"deploy/{REL}-{name}", _first_container(name), since="10m"):
            leaks[name] = True
    nemo = _nemo_logs("10m")
    if canary in nemo:
        leaks["nemo"] = True
    assert not leaks, f"canary in logs: {sorted(leaks)}"

    assert "Entered verbose mode" not in nemo
    json_after = [line for line in nemo.splitlines() if '"uvicorn.access"' in line or '"nemoguardrails' in line]
    assert json_after, "NeMo emitted no JSON request logs after traffic (handler muted?)"
    for line in json_after[:20]:
        json.loads(line.split(" ", 1)[1] if line.startswith("[pod/") else line)


def _first_container(name: str) -> str:
    proc = kubectl_run(["get", f"deploy/{REL}-{name}", "-o", "jsonpath={.spec.template.spec.containers[0].name}"])
    return proc.stdout.strip()
