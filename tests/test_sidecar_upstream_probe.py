"""CE-21: the sidecar is not ready while a gateway upstream is unreachable, and says which one."""
import asyncio
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "images" / "sidecar"))
from zelkor_sidecar.egress import EgressConfig, UpstreamProbe  # noqa: E402

CFG = EgressConfig(llm_upstream="http://zelkor-platform-ai-gateway:80/v1", mcp_upstream="http://zelkor-platform-mcp/mcp")


class Net:
    def __init__(self):
        self.down = set()
        self.connects = 0

    async def resolve(self, host, port):
        return {"zelkor-platform-ai-gateway": "10.43.175.236", "zelkor-platform-mcp": "10.43.175.236"}[host]

    async def connect(self, ip, port):
        self.connects += 1
        if port in self.down:
            raise ConnectionRefusedError()


def _probe(net, now):
    return UpstreamProbe(CFG, resolve=net.resolve, connect=net.connect, clock=lambda: now[0])


def test_ready_when_both_upstreams_connect():
    net, now = Net(), [0.0]
    assert asyncio.run(_probe(net, now).check()) is True
    assert net.connects == 2


def test_unreachable_upstream_fails_readiness_and_logs_once(caplog):
    net, now = Net(), [0.0]
    probe = _probe(net, now)
    net.down.add(80)
    with caplog.at_level(logging.INFO, logger="zelkor-sidecar"):
        assert asyncio.run(probe.check()) is False
        now[0] = 30.0
        assert asyncio.run(probe.check()) is False
    errors = [r for r in caplog.records if getattr(r, "event", "") == "upstream_unreachable"]
    # Both upstreams use port 80 here; each reports once, not once per probe.
    assert sorted(r.upstream for r in errors) == ["llm", "mcp"]
    assert all(r.levelno == logging.ERROR and r.ip == "10.43.175.236" and "zelkor deploy" in r.hint for r in errors)


def test_recovery_is_logged_and_ready_again(caplog):
    net, now = Net(), [0.0]
    probe = _probe(net, now)
    net.down.add(80)
    asyncio.run(probe.check())
    net.down.clear()
    now[0] = 30.0
    with caplog.at_level(logging.INFO, logger="zelkor-sidecar"):
        assert asyncio.run(probe.check()) is True
    assert {r.upstream for r in caplog.records if getattr(r, "event", "") == "upstream_reachable"} == {"llm", "mcp"}


def test_results_are_cached_between_probes():
    net, now = Net(), [0.0]
    probe = _probe(net, now)
    asyncio.run(probe.check())
    now[0] = 5.0
    asyncio.run(probe.check())
    assert net.connects == 2


def test_unresolvable_name_reports_unresolved(caplog):
    async def no_name(host, port):
        raise OSError("no such host")

    probe = UpstreamProbe(CFG, resolve=no_name, connect=Net().connect, clock=lambda: 0.0)
    with caplog.at_level(logging.ERROR, logger="zelkor-sidecar"):
        assert asyncio.run(probe.check()) is False
    assert {r.ip for r in caplog.records} == {"unresolved"}
