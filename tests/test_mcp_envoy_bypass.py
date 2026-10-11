"""S-10 / P8: from sandbox worker, Envoy :9856 and backend :8080 must be refused."""
from __future__ import annotations

import pytest

from tests.helpers.ce8 import exec_python, network_policies_enabled, s10_from_pods, s10_targets


def test_s10_bypass_port_refused():
    if not network_policies_enabled():
        pytest.skip("security.networkPolicies.enabled is off")
    pods = s10_from_pods()
    targets = s10_targets()
    failures: list[str] = []
    for pod in pods:
        for host, port in targets:
            script = (
                "import socket,sys\n"
                "s=socket.socket(); s.settimeout(5.0)\n"
                f"err=s.connect_ex(({host!r},{port}))\n"
                "s.close(); sys.stdout.write(str(err))\n"
            )
            out = exec_python(pod, script, timeout=20)
            err = int(out.splitlines()[-1])
            if err == 0:
                failures.append(f"{pod} -> {host}:{port}")
    assert not failures, f"expected refusal, got connect_ex=0 for {failures}"
