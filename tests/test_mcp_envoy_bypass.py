"""L5 live: from worker/agent pods, Envoy :9856 and backend :8080 must be refused."""
from __future__ import annotations

import os

import pytest

from tests.helpers.kube import kubectl_run

pytestmark = pytest.mark.skipif(
    not os.environ.get("ZELKOR_TEST_BYPASS_TARGETS"),
    reason="ZELKOR_TEST_BYPASS_TARGETS not set (comma host:port pairs for L5)",
)


def _targets() -> list[tuple[str, int]]:
    raw = os.environ.get("ZELKOR_TEST_BYPASS_TARGETS", "")
    out: list[tuple[str, int]] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        host, port_s = part.rsplit(":", 1)
        out.append((host, int(port_s)))
    return out


def _from_pods() -> list[str]:
    raw = os.environ.get("ZELKOR_TEST_BYPASS_FROM", "")
    return [p.strip() for p in raw.split(",") if p.strip()]


_CASES = [
    (pod, host, port)
    for pod in (_from_pods() or ["skip"])
    for host, port in (_targets() or [("skip", 0)])
]


@pytest.mark.parametrize("pod,host,port", _CASES)
def test_l5_bypass_port_refused(pod: str, host: str, port: int):
    if pod == "skip" or host == "skip":
        pytest.skip("ZELKOR_TEST_BYPASS_FROM / targets missing")
    probe = (
        "import socket,sys\n"
        f"s=socket.socket(); s.settimeout(5.0)\n"
        f"err=s.connect_ex(({host!r},{port}))\n"
        "s.close(); sys.stdout.write(str(err))\n"
    )
    res = kubectl_run(
        ["exec", pod, "--", "python3", "-S", "-c", probe],
        timeout=20,
    )
    assert res.returncode == 0, res.stderr or res.stdout
    err = int((res.stdout or "").strip().splitlines()[-1])
    assert err != 0, f"expected refusal from {pod} to {host}:{port}, got connect_ex=0"
