"""Live agent_step logs: names only (no cluster)."""
import json
import logging
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "images" / "aegra"))
sys.path.insert(0, str(ROOT / "images" / "common"))

from agent_step import AgentStepCallback, emit_from_lc_event  # noqa: E402
from zelkor_logging import JsonFormatter  # noqa: E402


def test_sitecustomize_and_dockerfile_ship_agent_step():
    site = (ROOT / "images/aegra/sitecustomize.py").read_text()
    dockerfile = (ROOT / "images/aegra/Dockerfile").read_text()
    assert "install_agent_step_callback" in site
    assert "agent_step.py" in dockerfile


def test_on_tool_start_logs_name_not_args(caplog):
    cb = AgentStepCallback()
    rid = uuid4()
    secret = '{"query": "classified-payload"}'
    with caplog.at_level(logging.INFO, logger="zelkor-aegra-wrap"):
        cb.on_tool_start({"name": "deep_research"}, secret, run_id=rid, name="deep_research")
    rec = next(r for r in caplog.records if getattr(r, "event", None) == "agent_step")
    payload = json.loads(JsonFormatter().format(rec))
    assert payload["name"] == "deep_research"
    assert payload["kind"] == "tool"
    joined = json.dumps(payload) + caplog.text
    assert "classified-payload" not in joined
    assert "query" not in joined
    cb.on_tool_end("ok", run_id=rid)


def test_emit_from_lc_event_logs_tool_name():
    recs: list[logging.LogRecord] = []

    class H(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            recs.append(record)

    log = logging.getLogger("zelkor-aegra-wrap")
    handler = H()
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    try:
        emit_from_lc_event(
            {"event": "on_tool_start", "name": "tavily__tavily_research", "data": {"input": {"q": "secret"}}}
        )
    finally:
        log.removeHandler(handler)
    rec = next(r for r in recs if getattr(r, "event", None) == "agent_step")
    payload = json.loads(JsonFormatter().format(rec))
    assert payload["name"] == "tavily__tavily_research"
    assert "secret" not in json.dumps(payload)


def test_json_payload_has_name_not_args():
    record = logging.LogRecord(
        name="zelkor-aegra-wrap",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="agent step",
        args=(),
        exc_info=None,
    )
    record.event = "agent_step"
    record.kind = "tool"
    record.step = "deep_research"
    record.phase = "start"
    record.elapsed_s = 0
    payload = json.loads(JsonFormatter().format(record))
    assert payload["name"] == "deep_research"
    assert payload["kind"] == "tool"
    assert payload["event"] == "agent_step"
    assert "classified" not in json.dumps(payload)
