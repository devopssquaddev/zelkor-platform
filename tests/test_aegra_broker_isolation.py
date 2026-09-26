"""Front door must not consume Aegra's global Redis job queue."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _workload_agents_block(values_text: str) -> str:
    block = values_text.split("\n  agents:", 1)[1]
    return block.split("\n  intent:", 1)[0]


def _has_aegra_db_upgrade(text: str) -> bool:
    return "aegra db upgrade" in text or '"aegra", "db", "upgrade"' in text


def test_front_door_redis_broker_defaults_off():
    values = (ROOT / "charts/zelkor-platform/values.yaml").read_text()
    agents = _workload_agents_block(values)
    assert "redisBroker:" in agents
    broker = agents.split("redisBroker:", 1)[1]
    assert "enabled: false" in broker.split("\n", 8)[1]


def test_front_door_deployment_uses_broker_value_not_true_literal():
    text = (ROOT / "charts/zelkor-platform/templates/aegra/deployment.yaml").read_text()
    assert "REDIS_BROKER_ENABLED" in text
    assert "aegra.redisBroker" in text
    assert 'value: "true"' not in text.split("REDIS_BROKER_ENABLED", 1)[1][:400]


def test_worker_chart_enables_redis_broker():
    text = (ROOT / "charts/zelkor-agent/templates/deployment.yaml").read_text()
    block = text.split("REDIS_BROKER_ENABLED", 1)[1][:200]
    assert 'value: "true"' in block
    assert "REDIS_CHANNEL_PREFIX" in text
    assert "WORKER_QUEUE_KEY" in text


def test_front_door_cannot_claim_worker_jobs():
    """Empty-graph front door must not BLPOP aegra:jobs; workers own that queue."""
    front_values = (ROOT / "charts/zelkor-platform/values.yaml").read_text()
    agents = _workload_agents_block(front_values)
    broker = agents.split("redisBroker:", 1)[1]
    assert "enabled: false" in broker.split("\n", 8)[1]
    worker = (ROOT / "charts/zelkor-agent/templates/deployment.yaml").read_text()
    block = worker.split("REDIS_BROKER_ENABLED", 1)[1][:200]
    assert 'value: "true"' in block


def test_app_pods_disable_lifespan_migrations():
    front = (ROOT / "charts/zelkor-platform/templates/aegra/deployment.yaml").read_text()
    worker = (ROOT / "charts/zelkor-agent/templates/deployment.yaml").read_text()
    assert "RUN_MIGRATIONS_ON_STARTUP" in front
    assert "RUN_MIGRATIONS_ON_STARTUP" in worker
    assert '"false"' in worker.split("RUN_MIGRATIONS_ON_STARTUP", 1)[1][:120]
    assert 'name: migrate' in front
    assert 'command: ["aegra", "db", "upgrade"]' in front
    assert _has_aegra_db_upgrade(front)
    assert "migrate.py" not in front
    assert "aegra.cli.image" in front
    runtime_df = (ROOT / "images/aegra/Dockerfile").read_text()
    assert "migrate.py" not in runtime_df
    assert (ROOT / "images/aegra-cli/Dockerfile").is_file()


def test_aegra_live_probe_drain_and_otel_knobs():
    values = (ROOT / "charts/zelkor-platform/values.yaml").read_text()
    agents = _workload_agents_block(values)
    assert 'path: "/live"' in agents
    assert "terminationGracePeriodSeconds: 35" in agents
    assert "workerDrainTimeout: 30" in agents
    telemetry = values.split("\n  telemetry:", 1)[1].split("\nworkspace:", 1)[0]
    assert "aegraOtelTargets: ''" in telemetry
    helpers = (ROOT / "charts/zelkor-platform/templates/_helpers.tpl").read_text()
    front = (ROOT / "charts/zelkor-platform/templates/aegra/deployment.yaml").read_text()
    assert "OTEL_TARGETS" in helpers
    assert "zelkor-platform.aegraLangfuseOtelEnvFrom" in helpers
    assert "zelkor-platform.aegraLangfuseOtelEnvFrom" in front
    assert "LANGFUSE_HOST" not in helpers.split("zelkor-platform.aegraOtelEnv", 1)[1][:800]
    worker = (ROOT / "charts/zelkor-agent/templates/deployment.yaml").read_text()
    assert "WORKER_DRAIN_TIMEOUT" in worker
    assert "path: /live" in (ROOT / "charts/zelkor-agent/values.yaml").read_text()
