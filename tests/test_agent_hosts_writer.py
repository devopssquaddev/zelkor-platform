"""CE-21: the agent host-map writer resolves Services (following ExternalName) to ClusterIPs."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "mcp")))
from ops.agent_hosts import build_map, resolve_cluster_ip, run  # noqa: E402

NS = "zelkor"
DATAPLANE = "zelkor-zelkor-platform-dataplane.envoy-gateway-system.svc.cluster.local"


def _svc(kind="ClusterIP", ip="", external=""):
    spec = {"type": kind}
    if ip:
        spec["clusterIP"] = ip
    if external:
        spec["externalName"] = external
    return {"spec": spec}


SERVICES = {
    f"/api/v1/namespaces/{NS}/services/zelkor-platform-ai-gateway": _svc("ExternalName", external=DATAPLANE),
    f"/api/v1/namespaces/{NS}/services/zelkor-platform-mcp": _svc("ExternalName", external=DATAPLANE),
    "/api/v1/namespaces/envoy-gateway-system/services/zelkor-zelkor-platform-dataplane": _svc(ip="10.43.175.236"),
    f"/api/v1/namespaces/{NS}/services/zelkor-platform-postgresql":
        _svc("ExternalName", external=f"zelkor-platform-postgresql-rw.{NS}.svc.cluster.local"),
    f"/api/v1/namespaces/{NS}/services/zelkor-platform-postgresql-rw": _svc(ip="10.43.217.227"),
    f"/api/v1/namespaces/{NS}/services/zelkor-platform-langfuse": _svc(ip="10.43.245.107"),
    f"/api/v1/namespaces/{NS}/services/zelkor-platform-outside": _svc("ExternalName", external="api.github.com"),
    f"/api/v1/namespaces/{NS}/services/zelkor-platform-headless": _svc(ip="None"),
}


def _get(objects):
    return lambda path: objects.get(path)


def test_external_name_is_followed_to_the_target_cluster_ip():
    assert resolve_cluster_ip(_get(SERVICES), "zelkor-platform-ai-gateway", NS) == "10.43.175.236"
    assert resolve_cluster_ip(_get(SERVICES), "zelkor-platform-postgresql", NS) == "10.43.217.227"


def test_outside_targets_headless_and_missing_services_are_skipped():
    get = _get(SERVICES)
    assert resolve_cluster_ip(get, "zelkor-platform-outside", NS) is None
    assert resolve_cluster_ip(get, "zelkor-platform-headless", NS) is None
    assert resolve_cluster_ip(get, "zelkor-platform-nope", NS) is None


def test_map_has_short_and_fqdn_keys_and_gateway_names_share_one_ip():
    data = build_map(_get(SERVICES), ["zelkor-platform-ai-gateway", "zelkor-platform-mcp",
                                      "zelkor-platform-langfuse", "zelkor-platform-nope"], NS)
    assert data["zelkor-platform-ai-gateway"] == data["zelkor-platform-mcp"] == "10.43.175.236"
    assert data[f"zelkor-platform-mcp.{NS}.svc.cluster.local"] == "10.43.175.236"
    assert data["zelkor-platform-langfuse"] == "10.43.245.107"
    assert not any(k.startswith("zelkor-platform-nope") for k in data)


def test_run_waits_for_required_services_then_writes_once():
    objects = {k: v for k, v in SERVICES.items() if "ai-gateway" not in k}
    writes = []
    calls = {"n": 0}

    def sleep(_s):
        calls["n"] += 1
        objects[f"/api/v1/namespaces/{NS}/services/zelkor-platform-ai-gateway"] = \
            _svc("ExternalName", external=DATAPLANE)

    rc = run(lambda p: objects.get(p), lambda path, body, method: writes.append((path, method, body)),
             services=["zelkor-platform-ai-gateway", "zelkor-platform-mcp"],
             required=["zelkor-platform-ai-gateway", "zelkor-platform-mcp"], namespace=NS,
             configmap="zelkor-platform-agent-hosts", release="zelkor-platform", deadline_s=60,
             sleep=sleep, clock=lambda: 0.0)
    assert rc == 0 and calls["n"] == 1
    assert len(writes) == 1 and writes[0][1] == "POST"
    assert writes[0][2]["data"]["zelkor-platform-ai-gateway"] == "10.43.175.236"


def test_run_fails_when_required_services_never_resolve():
    ticks = iter([0.0, 0.0, 100.0])
    rc = run(lambda p: None, lambda *a: None, services=["zelkor-platform-ai-gateway"],
             required=["zelkor-platform-ai-gateway"], namespace=NS, configmap="m", release="r",
             deadline_s=50, sleep=lambda _s: None, clock=lambda: next(ticks))
    assert rc == 1


def test_existing_configmap_is_replaced():
    objects = dict(SERVICES)
    objects[f"/api/v1/namespaces/{NS}/configmaps/m"] = {"data": {}}
    writes = []
    run(lambda p: objects.get(p), lambda path, body, method: writes.append((path, method)),
        services=["zelkor-platform-mcp"], required=["zelkor-platform-mcp"], namespace=NS,
        configmap="m", release="r", deadline_s=1, sleep=lambda _s: None, clock=lambda: 0.0)
    assert writes == [(f"/api/v1/namespaces/{NS}/configmaps/m", "PUT")]
