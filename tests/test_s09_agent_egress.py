"""S-09 / P8: agent pod cannot TCP to Qdrant, worker, extra MCP, public IP."""
from __future__ import annotations

import pytest

from tests.helpers.ce8 import agent_pod, exec_python, network_policies_enabled, s09_targets


def test_s09_agent_pod_tcp_refused():
    if not network_policies_enabled():
        pytest.skip("security.networkPolicies.enabled is off")
    pod = agent_pod()
    failures: list[str] = []
    for host, port, label in s09_targets():
        script = (
            "import socket,sys\n"
            "s=socket.socket(); s.settimeout(5.0)\n"
            f"err=s.connect_ex(({host!r},{port}))\n"
            "s.close(); sys.stdout.write(str(err))\n"
        )
        out = exec_python(pod, script, timeout=20)
        err = int(out.splitlines()[-1])
        if err == 0:
            failures.append(f"{label} {host}:{port}")
    assert not failures, f"expected refuse from {pod} to {failures}"
