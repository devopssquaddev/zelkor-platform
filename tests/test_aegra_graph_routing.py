"""Chart and image contract: Envoy routes graph_id; no Python Agent Protocol proxy."""
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
PLATFORM_CHART = ROOT / "charts/zelkor-platform"
AGENT_CHART = ROOT / "charts/zelkor-agent"
LOCAL_VALUES = ROOT / "profiles/values-local.yaml"


def test_graph_router_proxy_removed():
    assert not (ROOT / "images/aegra/graph_router.py").exists()
    dockerfile = (ROOT / "images/aegra/Dockerfile").read_text()
    assert "aegra_api.main:app" in dockerfile
    assert "graph_router" not in dockerfile
    front = (PLATFORM_CHART / "templates/aegra/deployment.yaml").read_text()
    worker = (AGENT_CHART / "templates/deployment.yaml").read_text()
    assert "aegra_api.main:app" in front
    assert "aegra_api.main:app" in worker
    assert "AEGRA_WORKERS" not in front
    assert "AEGRA_WORKERS" not in worker
    assert "graph_router" not in front
    assert "graph_router" not in worker


def test_workers_default_empty_and_not_urls():
    values = (PLATFORM_CHART / "values.yaml").read_text()
    aegra = values.split("\naegra:", 1)[1].split("\nguardrails:", 1)[0]
    assert "workers: []" in aegra
    assert "localhost" not in aegra
    assert "http://" not in aegra.split("workers:", 1)[1].split("\n", 8)[0]


def test_sitecustomize_has_ready_gate_not_proxy():
    text = (ROOT / "images/aegra/sitecustomize.py").read_text()
    assert "inject_ready" in text
    assert "proxy_to_worker" not in text
    assert "httpx.AsyncClient" not in text


def _helm(*args: str) -> str:
    try:
        res = subprocess.run(
            ["helm", *args],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        pytest.skip("helm not installed")
    if res.returncode != 0:
        pytest.fail(res.stderr or res.stdout)
    return res.stdout


def _docs(rendered: str) -> list:
    return [d for d in yaml.safe_load_all(rendered) if d]


def test_platform_httproute_single_backend_is_catch_all():
    rendered = _helm(
        "template",
        "zelkor",
        str(PLATFORM_CHART),
        "-f",
        str(LOCAL_VALUES),
        "-s",
        "templates/gateway/httproutes.yaml",
    )
    routes = [d for d in _docs(rendered) if d.get("metadata", {}).get("name", "").endswith("-aegra-route")]
    assert len(routes) == 1
    rules = routes[0]["spec"]["rules"]
    assert len(rules) == 1
    matches = rules[0]["matches"]
    assert matches == [{"path": {"type": "PathPrefix", "value": "/"}}]
    assert "X-Graph-ID" not in yaml.dump(rules)


def test_platform_httproute_workers_match_header_and_query():
    rendered = _helm(
        "template",
        "zelkor",
        str(PLATFORM_CHART),
        "-f",
        str(LOCAL_VALUES),
        "--set",
        "aegra.workers[0].graphId=fraud",
        "--set",
        "aegra.workers[0].service=fraud-agent",
        "--set",
        "aegra.workers[0].port=8000",
        "-s",
        "templates/gateway/httproutes.yaml",
    )
    routes = [d for d in _docs(rendered) if d.get("metadata", {}).get("name", "").endswith("-aegra-route")]
    assert len(routes) == 1
    rules = routes[0]["spec"]["rules"]
    assert len(rules) == 2
    worker, default = rules
    dumped = yaml.dump(worker)
    assert "X-Graph-ID" in dumped
    assert "graph_id" in dumped
    assert "fraud" in dumped
    assert worker["backendRefs"][0]["name"] == "fraud-agent"
    assert int(worker["backendRefs"][0]["port"]) == 8000
    assert default["backendRefs"][0]["name"].endswith("-aegra")
    assert default["matches"][0]["path"]["value"] == "/"
    assert "http://" not in dumped


def test_aegra_sse_backend_traffic_policy():
    rendered = _helm(
        "template",
        "zelkor",
        str(PLATFORM_CHART),
        "-f",
        str(LOCAL_VALUES),
        "-s",
        "templates/gateway/aegra-backendtrafficpolicy.yaml",
    )
    docs = _docs(rendered)
    assert docs
    policy = docs[0]
    assert policy["kind"] == "BackendTrafficPolicy"
    timeout = policy["spec"]["timeout"]["http"]
    assert timeout["streamIdleTimeout"]
    assert timeout.get("requestTimeout") in ("0s", "0")
    assert policy["spec"].get("requestBuffer") in (None, {})


def test_agent_chart_redis_prefix_and_shared_route():
    rendered = _helm(
        "template",
        "fraud",
        str(AGENT_CHART),
        "--set",
        "graphId=fraud",
        "--set",
        "platform.databaseUrl=postgresql://zelkor:x@db:5432/aegra",
        "--set",
        "sharedRoute.enabled=true",
        "--set",
        "sharedRoute.host=aegra.example",
        "--set",
        "sharedRoute.gatewayName=zelkor-platform-gateway",
    )
    docs = _docs(rendered)
    kinds = {d["kind"]: d for d in docs}
    deploy = kinds["Deployment"]
    env = {e["name"]: e.get("value") for e in deploy["spec"]["template"]["spec"]["containers"][0]["env"]}
    assert env["REDIS_CHANNEL_PREFIX"] == "aegra:fraud:run:"
    assert env["WORKER_QUEUE_KEY"] == "aegra:fraud:jobs"
    assert env["REDIS_BROKER_ENABLED"] == "true"
    assert "AEGRA_WORKERS" not in env
    route = kinds["HTTPRoute"]
    dumped = yaml.dump(route)
    assert "X-Graph-ID" in dumped
    assert "graph_id" in dumped
    assert route["spec"]["hostnames"] == ["aegra.example"]
    assert route["spec"]["rules"][0]["backendRefs"][0]["name"] == "fraud-zelkor-agent"
