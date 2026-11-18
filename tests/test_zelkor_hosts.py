"""CE-21 CLI: zelkor deploy fills hostAliases from the host map; zelkor verify --hosts finds drift."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli" / "src"))
from zelkor.envfile import Env  # noqa: E402
from zelkor.hosts_check import check_agent_hosts  # noqa: E402
from zelkor.main import (PlatformInfo, _apply_host_aliases, host_aliases_from_map,  # noqa: E402
                         load_host_aliases)

ENV = Env(name="l", kube_context="kind-zelkor", namespace="zelkor")
GW = "10.43.175.236"
MAP = {"zelkor-platform-ai-gateway": GW, "zelkor-platform-mcp": GW,
       "zelkor-platform-ai-gateway.zelkor.svc.cluster.local": GW, "zelkor-platform-postgresql": "10.43.217.227"}


def _ok(obj):
    return SimpleNamespace(returncode=0, stdout=json.dumps(obj), stderr="")


MISSING = SimpleNamespace(returncode=1, stdout="", stderr="NotFound")


def test_map_groups_hostnames_per_ip_in_stable_order():
    assert host_aliases_from_map(MAP) == [
        {"ip": GW, "hostnames": ["zelkor-platform-ai-gateway", "zelkor-platform-ai-gateway.zelkor.svc.cluster.local",
                                 "zelkor-platform-mcp"]},
        {"ip": "10.43.217.227", "hostnames": ["zelkor-platform-postgresql"]},
    ]


def test_platform_without_contract_key_is_skipped():
    info = PlatformInfo(release="zelkor-platform")
    load_host_aliases(ENV, info, runner=lambda *a, **k: pytest.fail("must not read"), wait_sec=0)
    overlay: dict = {}
    _apply_host_aliases(overlay, info)
    assert overlay == {}


def test_deploy_waits_for_the_map_then_fills_platform_host_aliases():
    info = PlatformInfo(release="zelkor-platform", agent_hosts_configmap="zelkor-platform-agent-hosts")
    calls = {"n": 0}

    def runner(argv, **_k):
        calls["n"] += 1
        return MISSING if calls["n"] == 1 else _ok({"data": MAP})

    load_host_aliases(ENV, info, runner=runner, wait_sec=60, sleep=lambda _s: None)
    overlay: dict = {"platform": {"releaseName": "zelkor-platform"}}
    _apply_host_aliases(overlay, info)
    assert calls["n"] == 2
    assert overlay["platform"]["hostAliases"][0]["ip"] == GW


def test_deploy_fails_naming_the_writer_job_when_the_map_never_appears():
    info = PlatformInfo(release="zelkor-platform", agent_hosts_configmap="zelkor-platform-agent-hosts")
    with pytest.raises(RuntimeError, match="zelkor-platform-agent-hosts-<revision>"):
        load_host_aliases(ENV, info, runner=lambda *a, **k: MISSING, wait_sec=0, sleep=lambda _s: None)


def _cluster(*, live_gw=GW, pod_aliases=None, upstreams="", annotations=None, lockdown="on"):
    contract = {"data": {"AGENT_HOSTS_CONFIGMAP": "zelkor-platform-agent-hosts", "HTTP_APIS": "github"}}
    services = {
        "zelkor-platform-ai-gateway": {"spec": {"type": "ExternalName",
                                                "externalName": "dp.envoy-gateway-system.svc.cluster.local"}},
        "zelkor-platform-mcp": {"spec": {"type": "ExternalName",
                                         "externalName": "dp.envoy-gateway-system.svc.cluster.local"}},
        "dp": {"spec": {"type": "ClusterIP", "clusterIP": live_gw}},
        "zelkor-platform-postgresql": {"spec": {"type": "ClusterIP", "clusterIP": "10.43.217.227"}},
    }
    labels = {"zelkor.io/workload-type": "agent", "zelkor.io/platform-release": "zelkor-platform"}
    if lockdown:
        labels["zelkor.io/dns-lockdown"] = lockdown
    env = [{"name": "ZELKOR_API_UPSTREAMS", "value": upstreams}] if upstreams else []
    pod = {"metadata": {"namespace": "zelkor", "name": "rt-pydantic-x", "labels": labels,
                        "annotations": annotations or {}},
           "spec": {"hostAliases": pod_aliases if pod_aliases is not None else host_aliases_from_map(MAP),
                    "containers": [{"name": "sidecar", "env": env}]}}

    def runner(argv, **_k):
        if "configmap" in argv:
            name = argv[argv.index("configmap") + 1]
            return _ok(contract) if name == "zelkor-platform-contract" else _ok({"data": MAP})
        if "svc" in argv:
            svc = services.get(argv[argv.index("svc") + 1])
            return _ok(svc) if svc else MISSING
        if "pods" in argv:
            return _ok({"items": [pod]})
        return MISSING

    return runner


def _check(runner):
    return check_agent_hosts("zelkor-platform", "zelkor", kubectl=["kubectl"], runner=runner)


def test_healthy_lockdown_passes(capsys):
    assert _check(_cluster(upstreams="github=http://zelkor-platform-api-github")) == 0
    assert "FAIL" not in capsys.readouterr().out


def test_recreated_gateway_service_is_map_drift(capsys):
    assert _check(_cluster(live_gw="10.43.9.9")) == 1
    assert "live: 10.43.9.9" in capsys.readouterr().out


def test_pod_with_old_entries_is_drift(capsys):
    stale = [{"ip": "10.43.1.1", "hostnames": ["zelkor-platform-ai-gateway"]}]
    assert _check(_cluster(pod_aliases=stale)) == 1
    assert "FAIL pod hosts" in capsys.readouterr().out


def test_stale_http_api_name_is_reported(capsys):
    # demohetzner 2026-11-18: rt-pydantic still relayed to api-echo after the platform dropped it.
    assert _check(_cluster(upstreams="echo=http://zelkor-platform-api-echo,github=http://x")) == 1
    out = capsys.readouterr().out
    assert "zelkor-platform-api-echo has no route" in out and "PASS http api" in out


def test_inactive_lockdown_is_a_warning_not_a_failure(capsys):
    assert _check(_cluster(lockdown="", annotations={"zelkor.io/dns-lockdown": "inactive"})) == 0
    assert "WARN dns" in capsys.readouterr().out
