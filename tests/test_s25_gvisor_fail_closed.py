"""S-25 (P7) L2: the gVisor verify Job fails the release when runsc is not active and
security.sandbox.failClosed=true, and only warns when it is false (the documented opt-out).
The live half (RuntimeClass absent -> worker Pending, no runc pod) is test_s25_gvisor_live.py."""
from __future__ import annotations

import pytest

from tests.test_helm_gvisor_provisioning import _docs, _helm, _kinds

VERIFY = "zelkor-platform-gvisor-verify"


def _verify_script(*extra: str) -> str:
    proc = _helm("--set", "security.sandbox.provisioning.mode=daemonset", *extra)
    assert proc.returncode == 0, proc.stderr
    job = next(d for d in _kinds(_docs(proc.stdout), "Job") if d["metadata"]["name"] == VERIFY)
    spec = job["spec"]["template"]["spec"]
    assert spec["runtimeClassName"] == "gvisor"  # the probe itself must run under the sandbox runtime
    return spec["containers"][0]["command"][-1]


def _fallthrough(script: str) -> str:
    """The lines after the 'runsc not active' message: what happens when gVisor is missing."""
    return script.split("runsc not active", 1)[1]


def test_s25_fail_closed_true_exits_nonzero_without_gvisor():
    tail = _fallthrough(_verify_script("--set", "security.sandbox.failClosed=true"))
    assert "exit 1" in tail
    assert "exit 0" not in tail
    assert "continuing without gVisor" not in tail


@pytest.mark.parametrize("extra", [(), ("--set", "security.sandbox.failClosed=false")])
def test_s25_fail_closed_false_warns_and_continues(extra):
    tail = _fallthrough(_verify_script(*extra))
    assert "WARNING: failClosed=false; continuing without gVisor sandbox" in tail
    assert "exit 1" not in tail


def test_s25_verify_job_banner_check_precedes_exit():
    script = _verify_script("--set", "security.sandbox.failClosed=true")
    assert script.index("grep -qi gvisor") < script.index("exit 1")
