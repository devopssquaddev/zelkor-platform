"""S-25 (P7) L3: sandbox workers run only under gVisor, and a missing RuntimeClass fails closed.

Non-destructive on a shared lab: (1) every sandbox-worker pod requests the sandbox RuntimeClass and
is Running; (2) its kernel is gVisor, not the host's; (3) a pod that names a RuntimeClass that does
not exist is refused by the API server, so a missing gVisor never degrades to runc."""
from __future__ import annotations

import json
import os
import uuid

import pytest

from tests.helpers.kube import kubectl_cmd, kubectl_run, platform_contract

SELECTOR = "app.kubernetes.io/component=mcp-sandbox-worker"


@pytest.fixture(scope="module")
def workers() -> list[dict]:
    if not os.environ.get("KUBECONTEXT"):
        pytest.skip("KUBECONTEXT not set")
    if platform_contract().get("SANDBOX_ENABLED", "true").lower() == "false":
        pytest.skip("sandbox off in this install")
    r = kubectl_run(["get", "pods", "-l", SELECTOR, "-o", "json"])
    assert r.returncode == 0, r.stderr
    pods = [p for p in json.loads(r.stdout)["items"] if not p["metadata"].get("deletionTimestamp")]
    assert pods, "SANDBOX_ENABLED but no sandbox-worker pod"
    return pods


def test_s25_every_worker_requests_gvisor_and_runs(workers):
    bad = [f"{p['metadata']['name']}: runtimeClassName={p['spec'].get('runtimeClassName')!r} "
           f"phase={p['status'].get('phase')}" for p in workers
           if p["spec"].get("runtimeClassName") != "gvisor" or p["status"].get("phase") != "Running"]
    assert not bad, "\n".join(bad)


def test_s25_worker_kernel_is_gvisor(workers):
    name = workers[0]["metadata"]["name"]
    r = kubectl_run(["exec", name, "--", "sh", "-c", "dmesg 2>/dev/null | head -5; uname -r"], timeout=30)
    assert r.returncode == 0, f"exec in {name} failed: {r.stderr[-300:]}"
    assert "gvisor" in r.stdout.lower() or "starting gvisor" in r.stdout.lower(), \
        f"{name} does not run on the gVisor kernel: {r.stdout[:300]!r}"


def test_s25_pod_with_missing_runtimeclass_is_refused(workers):
    rc = f"gvisor-absent-{uuid.uuid4().hex[:6]}"
    pod = {"apiVersion": "v1", "kind": "Pod", "metadata": {"name": f"s25-probe-{uuid.uuid4().hex[:6]}"},
           "spec": {"runtimeClassName": rc, "restartPolicy": "Never",
                    "containers": [{"name": "c", "image": "busybox:1.38.0", "command": ["true"]}]}}
    import subprocess

    r = subprocess.run(kubectl_cmd("create", "--dry-run=server", "-f", "-"), input=json.dumps(pod),
                       capture_output=True, text=True, timeout=30)
    assert r.returncode != 0, "API server admitted a pod with a missing RuntimeClass (it would not run sandboxed)"
    assert "runtimeclass" in r.stderr.lower() or "not found" in r.stderr.lower(), r.stderr[:300]
