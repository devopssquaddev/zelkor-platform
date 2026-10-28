"""Live helpers for non-Aegra runtime agents behind zelkor-sidecar (UAT-24…27, S-74…S-82).

Env (all optional; tests skip without them):
  ZELKOR_RUNTIME_GRAPHS   comma list of deployed runtime graph ids (e.g. rt-pydantic,rt-crewai,rt-opencode)
  ZELKOR_TEST_TOKENS      JSON with "tenant-a" and "tenant-b" bearers (real IdP users on Path B)
  GATEWAY_BASE_URL / AEGRA_HOST_HEADER   agents front door; LANGFUSE_BASE_URL for traces
  KUBECONFIG + KUBECONTEXT              in-pod checks; never the default context
"""
from __future__ import annotations

import base64
import json
import os
import time
from typing import Any

import pytest

from tests.helpers.kube import kubectl_run
from tests.helpers.langfuse import list_observations, sandbox_execution_metadata
from tests.helpers.tokens import token_for

MKNOD = "import os\nos.mknod('/tmp/dev0', 0o600 | 0o020000, os.makedev(1, 3))\nprint('created')"
SANDBOX_PROMPT = ("Call the sandbox__execute_python tool exactly once with timeout 30 and this code, "
                  "then report what happened:\n" + MKNOD)


def runtime_graphs() -> list[str]:
    graphs = [g.strip() for g in os.environ.get("ZELKOR_RUNTIME_GRAPHS", "").split(",") if g.strip()]
    if not graphs:
        pytest.skip("ZELKOR_RUNTIME_GRAPHS not set")
    return graphs


def require_kube() -> None:
    if not os.environ.get("KUBECONTEXT", "").strip():
        pytest.skip("KUBECONTEXT not set (in-pod checks never use the default context)")


def tenant_token(key: str) -> str:
    try:
        return token_for(key)
    except KeyError:
        pytest.skip(f"no {key} token in ZELKOR_TEST_TOKENS")


def tenant_id(token: str) -> str:
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    claims = json.loads(base64.urlsafe_b64decode(payload))
    return str(claims.get("tenant_id") or claims.get("org_id") or claims.get("sub") or "")


def client(graph: str, token: str):
    from langgraph_sdk import get_sync_client

    headers = {"Authorization": f"Bearer {token}", "X-Graph-ID": graph}
    host = os.environ.get("AEGRA_HOST_HEADER", "").strip()
    if host and not os.environ.get("GATEWAY_BASE_URL", "").startswith("https://"):
        headers["Host"] = host
    return get_sync_client(url=os.environ.get("GATEWAY_BASE_URL", "http://127.0.0.1:8088"),
                           headers=headers, timeout=(5.0, 300.0, 300.0, 5.0))


def run(graph: str, token: str, prompt: str) -> tuple[str, Any]:
    c = client(graph, token)
    thread = c.threads.create()["thread_id"]
    out = c.runs.wait(thread, graph, input={"messages": [{"role": "human", "content": prompt}]})
    return thread, out


def run_error(out: Any) -> Any:
    return out.get("__error__") if isinstance(out, dict) else None


def trace_for_thread(thread_id: str, *, graph: str, want_tool: bool, timeout: float = 120.0) -> list[dict]:
    """Full observations of the run's trace once the root (and a TOOL span, if wanted) landed."""
    deadline = time.monotonic() + timeout
    full: list[dict] = []
    while time.monotonic() < deadline:
        rows = list_observations(session_id=thread_id, limit=100)
        if rows:
            full = list_observations(trace_id=rows[0]["traceId"], limit=100)
            roots = {str(o.get("name")) for o in full if not o.get("parentObservationId")}
            tool_ok = not want_tool or any(str(o.get("type")).upper() == "TOOL" for o in full)
            if graph in roots and tool_ok:
                return full
        time.sleep(3)
    return full


def tool_spans(observations: list[dict]) -> list[dict]:
    return [o for o in observations if str(o.get("type")).upper() == "TOOL"]


def error_spans(observations: list[dict]) -> list[str]:
    return sorted(str(o.get("name")) for o in observations if str(o.get("level")).upper() == "ERROR")


def sandbox_run(graph: str, token: str, *, attempts: int = 3) -> tuple[list[dict], dict | None]:
    """Ask for one denied sandbox call; retry when the model skips the tool (model behavior, not product)."""
    full: list[dict] = []
    for _ in range(attempts):
        thread, out = run(graph, token, SANDBOX_PROMPT)
        assert run_error(out) is None, run_error(out)
        full = trace_for_thread(thread, graph=graph, want_tool=True)
        if tool_spans(full):
            return full, sandbox_execution_metadata(full)
    return full, None


def deployment(graph: str) -> str:
    return f"deploy/{graph}-zelkor-agent"


def exec_python(graph: str, container: str, script: str, timeout: int = 120) -> str:
    """Run a Python script inside one container of the agent pod (stdin, no args with secrets)."""
    import subprocess

    from tests.helpers.kube import kubectl_cmd

    proc = subprocess.run(kubectl_cmd("exec", "-i", deployment(graph), "-c", container, "--", "python", "-"),
                          input=script, capture_output=True, text=True, timeout=timeout, check=False)
    assert proc.returncode == 0, proc.stderr[-500:]
    return proc.stdout


def container_logs(target: str, container: str, since: str = "15m") -> str:
    proc = kubectl_run(["logs", target, "-c", container, f"--since={since}"], timeout=60)
    return proc.stdout
