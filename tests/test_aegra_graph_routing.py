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
    wrap = (ROOT / "images/aegra/trace_wrap.py").read_text()
    assert "inject_ready" in text
    assert "proxy_to_worker" not in text
    assert "disable_streaming" in text
    assert "trace_wrap" in text
    assert "patch_otel_setup" in text
    assert "ChatOpenAI.request" in wrap
    assert "_agenerate" in wrap
    assert "httpx2" in wrap
    assert "BaseChatOpenAI" in wrap
    assert "Pregel" in wrap
    assert "astream_events" in wrap
    assert "HTTPXClientInstrumentor(" not in wrap


def test_nemo_content_safety_passthrough_for_tools():
    rendered = _helm(
        "template",
        "zelkor",
        str(PLATFORM_CHART),
        "-f",
        str(LOCAL_VALUES),
        "-s",
        "templates/guardrails/configmap.yaml",
    )
    assert "passthrough: true" in rendered
    assert "name: OpenTelemetry" in rendered
    assert "enable_content_capture: true" in rendered
    assert "check finserve topic" not in rendered
    assert "regex_detection" not in rendered
    assert "embeddings_only: true" not in rendered
    extra = _helm(
        "template",
        "zelkor",
        str(PLATFORM_CHART),
        "-f",
        str(LOCAL_VALUES),
        "--set",
        "guardrails.nemo.extraInputFlows[0]=check-topic",
        "-s",
        "templates/guardrails/configmap.yaml",
    )
    assert "- check-topic" in extra
    deploy = _helm(
        "template",
        "zelkor",
        str(PLATFORM_CHART),
        "-f",
        str(LOCAL_VALUES),
        "-s",
        "templates/guardrails/deployment.yaml",
    )
    assert "checksum/config" in deploy
    assert "opentelemetry-instrument" in deploy
    assert "OTEL_METRICS_EXPORTER" in deploy
    assert "OTEL_PYTHON_FASTAPI_EXCLUDED_URLS" in deploy
    assert "/v1/health" in deploy
    assert "path: /v1/health" in deploy
    assert "/v1/rails/configs" not in deploy
    assert "--disable-chat-ui" in deploy
    assert "NEMO_GUARDRAILS_NO_USAGE_STATS" in deploy
    off = _helm(
        "template",
        "zelkor",
        str(PLATFORM_CHART),
        "-f",
        str(LOCAL_VALUES),
        "--set",
        "guardrails.nemo.observability.otel.enabled=false",
        "-s",
        "templates/guardrails/configmap.yaml",
    )
    assert "name: OpenTelemetry" not in off
    assert "enable_content_capture" not in off
    capture_off = _helm(
        "template",
        "zelkor",
        str(PLATFORM_CHART),
        "-f",
        str(LOCAL_VALUES),
        "--set",
        "guardrails.nemo.observability.otel.captureContent=false",
        "-s",
        "templates/guardrails/configmap.yaml",
    )
    assert "enable_content_capture: false" in capture_off
    off_deploy = _helm(
        "template",
        "zelkor",
        str(PLATFORM_CHART),
        "-f",
        str(LOCAL_VALUES),
        "--set",
        "guardrails.nemo.observability.otel.enabled=false",
        "-s",
        "templates/guardrails/deployment.yaml",
    )
    assert "opentelemetry-instrument" not in off_deploy
    assert "--disable-chat-ui" in off_deploy
    assert "path: /v1/health" in off_deploy
    assert "NEMO_GUARDRAILS_NO_USAGE_STATS" in off_deploy


def test_nemo_otel_uses_instrument_not_sitecustomize():
    dockerfile = (ROOT / "images/guardrails/Dockerfile").read_text()
    reqs = (ROOT / "images/guardrails/requirements.txt").read_text()
    assert "sitecustomize" not in dockerfile
    assert not (ROOT / "images/guardrails/sitecustomize.py").exists()
    assert "opentelemetry-distro==0.65b0" in reqs
    assert "opentelemetry-instrumentation-fastapi==0.65b0" in reqs
    assert "opentelemetry-instrumentation-asgi==0.65b0" in reqs
    assert "opentelemetry-instrumentation-httpx==0.65b0" in reqs
    assert '"nemoguardrails", "server"' in dockerfile
    assert "--disable-chat-ui" in dockerfile
    aegra_reqs = (ROOT / "images/aegra/requirements.txt").read_text()
    assert "opentelemetry-instrumentation-httpx==0.65b0" in aegra_reqs


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


def test_agent_chart_graph_ids_share_one_service():
    rendered = _helm(
        "template",
        "desk",
        str(AGENT_CHART),
        "--set",
        "graphIds[0]=advisor",
        "--set",
        "graphIds[1]=research",
        "--set",
        "aegraConfig=/app/aegra-desk.json",
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
    assert env["ZELKOR_GRAPH_ID"] == "advisor"
    assert env["AEGRA_CONFIG"] == "/app/aegra-desk.json"
    route = kinds["HTTPRoute"]
    dumped = yaml.dump(route)
    assert dumped.count("X-Graph-ID") == 2
    assert "advisor" in dumped
    assert "research" in dumped
    assert len(route["spec"]["rules"]) == 1
    assert route["spec"]["rules"][0]["backendRefs"][0]["name"] == "desk-zelkor-agent"


def test_agent_chart_shared_route_emits_when_host_and_gateway_set():
    """CE-1: HTTPRoute when host + gatewayName are set; enabled is not required."""
    rendered = _helm(
        "template",
        "fraud",
        str(AGENT_CHART),
        "--set",
        "graphId=fraud",
        "--set",
        "platform.databaseUrl=postgresql://zelkor:x@db:5432/aegra",
        "--set",
        "sharedRoute.host=aegra.example",
        "--set",
        "sharedRoute.gatewayName=zelkor-platform-gateway",
    )
    docs = _docs(rendered)
    routes = [d for d in docs if d.get("kind") == "HTTPRoute"]
    assert len(routes) == 1
    assert routes[0]["spec"]["hostnames"] == ["aegra.example"]
    dumped = yaml.dump(routes[0])
    assert "X-Graph-ID" in dumped
    assert "fraud" in dumped


def test_agent_chart_no_shared_route_without_host():
    rendered = _helm(
        "template",
        "fraud",
        str(AGENT_CHART),
        "--set",
        "graphId=fraud",
        "--set",
        "platform.databaseUrl=postgresql://zelkor:x@db:5432/aegra",
        "--set",
        "sharedRoute.gatewayName=zelkor-platform-gateway",
    )
    docs = _docs(rendered)
    assert not any(d.get("kind") == "HTTPRoute" for d in docs)
