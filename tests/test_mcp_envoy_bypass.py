"""L5 live: direct backend :8080 / sandbox :9856 must be refused (NetworkPolicy)."""
from __future__ import annotations

import os
import socket

import pytest

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


@pytest.mark.parametrize("host,port", _targets() or [("skip", 0)])
def test_l5_bypass_port_refused(host: str, port: int):
    if host == "skip":
        pytest.skip("no bypass targets")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2.0)
    try:
        err = sock.connect_ex((host, port))
    finally:
        sock.close()
    assert err != 0, f"expected refusal for {host}:{port}"
