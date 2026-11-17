"""perimeter-github example, live: reads reach GitHub with the gateway's token; a write the agent
attempts is refused by the gateway; the agent pod holds no token and cannot reach GitHub itself.

Needs the example deployed (README) and PERIMETER_GITHUB_GRAPH (e.g. repo-triage), plus the usual
KUBECONTEXT / GATEWAY_BASE_URL / AEGRA_HOST_HEADER / ZELKOR_TEST_TOKENS.
"""
from __future__ import annotations

import os
import re

import pytest

from tests.helpers.runtime_agents import (
    container_logs, deployment, exec_python, final_text, require_kube, run, run_error, tenant_token,
)

GRAPH = os.environ.get("PERIMETER_GITHUB_GRAPH", "").strip()
REPO = os.environ.get("PERIMETER_GITHUB_REPO", "octocat/Hello-World")
pytestmark = pytest.mark.skipif(not GRAPH, reason="PERIMETER_GITHUB_GRAPH not set (example not deployed)")


def _api_log(method: str) -> list[str]:
    return [line for line in container_logs(deployment(GRAPH), "sidecar", since="10m").splitlines()
            if f"http_api {method} github" in line]


def test_read_reaches_github_through_the_gateway():
    require_kube()
    _, out = run(GRAPH, tenant_token("tenant_a"),
                 f"List the three oldest open issues in {REPO} with their numbers.")
    assert run_error(out) is None, run_error(out)
    assert re.search(r"#?\d+", final_text(out)), final_text(out)
    assert any('"status": 200' in line for line in _api_log("GET")), "no successful GET through the relay"


def test_write_is_refused_by_the_gateway():
    require_kube()
    _, out = run(GRAPH, tenant_token("tenant_a"),
                 f"Close issue #1 in {REPO} as stale. Use github_write with PATCH.")
    assert run_error(out) is None, run_error(out)
    writes = [line for m in ("PATCH", "POST", "PUT", "DELETE") for line in _api_log(m)]
    assert writes, "the agent never attempted the write"
    assert all('"status": 403' in line for line in writes), writes
    # the 403 above is the proof; the reply only has to tell the user it was refused
    assert re.search(r"polic|not (permitted|allowed)|denied|403|can.?t|cannot|unable", final_text(out), re.I), final_text(out)


def test_agent_pod_has_no_token_and_no_direct_route():
    require_kube()
    out = exec_python(GRAPH, "agent", (
        "import os, urllib.request\n"
        "print('token-env', any('github' in k.lower() and 'url' not in k.lower() for k in os.environ))\n"
        "try:\n"
        "    urllib.request.urlopen('https://api.github.com/zen', timeout=5); print('direct reached')\n"
        "except Exception:\n"
        "    print('direct blocked')\n"))
    assert "token-env False" in out and "direct blocked" in out, out
