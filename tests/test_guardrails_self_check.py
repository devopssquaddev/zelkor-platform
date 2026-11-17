"""zelkor_self_check: JSON verdict, log mode never refuses, unclear or slow answers let the request through."""
import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "images" / "guardrails"))

import zelkor_self_check as sc  # noqa: E402


@pytest.mark.parametrize("raw,expected", [
    ('{"block": true}', True),
    ('{"block": false}', False),
    ('<think>harmful?</think>\n```json\n{"block": true}\n```', True),
    ("Yes", None),
    ("Sure, here is the answer: 4", None),
    ('{"block": "maybe"}', None),
])
def test_parse_verdict(raw, expected):
    assert sc.parse_verdict(raw) is expected


def _run(answer=None, delay=0.0, error=None, mode="block", timeout_ms=1500, on_unavailable="allow"):
    async def fake_task(**_):
        if delay:
            await asyncio.sleep(delay)
        if error:
            raise error
        return True, answer

    return asyncio.run(sc.check(side="input", mode=mode, timeout_ms=timeout_ms,
                                text="some text", run_task=fake_task, on_unavailable=on_unavailable))


def test_block_mode_refuses_on_a_block_verdict():
    assert _run('{"block": true}')["blocked"] is True


def test_log_mode_never_refuses():
    verdict = _run('{"block": true}', mode="log")
    assert verdict == {"blocked": False, "verdict": "block", "status": "ok", "mode": "log",
                       "enforced": False, "on_unavailable": "allow"}


def test_unclear_answer_lets_the_request_through():
    assert _run("Yes")["blocked"] is False
    assert _run("Yes")["status"] == "unparseable"


def test_timeout_lets_the_request_through():
    verdict = _run('{"block": true}', delay=0.2, timeout_ms=50)
    assert verdict["blocked"] is False and verdict["status"] == "timeout"


def test_backend_error_lets_the_request_through():
    assert _run(error=RuntimeError("502"))["status"] == "error"


def test_empty_text_is_not_checked():
    async def never(**_):
        raise AssertionError("called")

    verdict = asyncio.run(sc.check(side="input", mode="block", timeout_ms=100, text="", run_task=never))
    assert verdict["blocked"] is False and verdict["status"] == "skipped"


# -- 2.5.4: onUnavailable and trace tags ---------------------------------------------------

@pytest.mark.parametrize("kw,status", [
    ({"answer": '{"block": false}', "delay": 0.2, "timeout_ms": 50}, "timeout"),
    ({"error": RuntimeError("502")}, "error"),
    ({"answer": "Yes"}, "unparseable"),
])
def test_block_mode_can_fail_closed_when_no_verdict(kw, status):
    v = _run(mode="block", on_unavailable="block", **kw)
    assert (v["status"], v["blocked"], v["enforced"]) == (status, True, True)


def test_on_unavailable_block_never_applies_to_log_mode():
    v = _run(error=RuntimeError("502"), mode="log", on_unavailable="block")
    assert (v["blocked"], v["enforced"]) == (False, False)


def test_enforced_only_when_block_mode_refuses():
    assert _run('{"block": true}', mode="block")["enforced"] is True
    assert _run('{"block": false}', mode="block")["enforced"] is False


def test_every_check_is_tagged_in_the_trace(monkeypatch):
    spans = []
    monkeypatch.setattr(sc, "_record_span", lambda side, attrs, error="": spans.append((side, attrs)))
    _run('{"block": true}', mode="log")
    _run('{"block": false}', delay=0.2, timeout_ms=50, mode="block")
    (side, a), (_, b) = spans
    assert side == "input"
    assert (a["zelkor.guardrail.mode"], a["zelkor.guardrail.verdict"], a["zelkor.guardrail.status"],
            a["zelkor.guardrail.enforced"]) == ("log", "block", "ok", False)
    assert a["langfuse.observation.metadata.guardrail_mode"] == "log"
    assert (b["zelkor.guardrail.status"], b["zelkor.guardrail.verdict"]) == ("timeout", "none")
    assert b["zelkor.guardrail.latency_ms"] >= 0


def test_span_failure_never_changes_a_verdict(monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("no tracer")
    monkeypatch.setattr(sc, "_record_span", boom)
    assert _run('{"block": true}', mode="block")["blocked"] is True


def test_check_without_verdict_is_an_error_span(monkeypatch):
    spans = []
    monkeypatch.setattr(sc, "_record_span", lambda side, attrs, error="": spans.append((attrs, error)))
    _run('{"block": false}', mode="log")
    _run('{"block": false}', delay=0.2, timeout_ms=50, mode="log")
    _run(error=RuntimeError("429"), mode="block", on_unavailable="block")
    (ok, ok_err), (timeout, timeout_err), (error, error_err) = spans
    assert ok_err == "" and "error.type" not in ok
    assert (timeout["error.type"], timeout_err) == ("timeout", "self-check timeout; request allowed")
    assert (error["error.type"], error_err) == ("error", "self-check error; request refused")
    assert not any(k.startswith("langfuse.observation.level") for a, _ in spans for k in a)


def test_record_span_sets_error_status():
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from opentelemetry.trace import StatusCode

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("t")
    import opentelemetry.trace as ot

    orig = ot.get_tracer
    ot.get_tracer = lambda *_a, **_k: tracer
    try:
        sc._record_span("input", {"zelkor.guardrail.status": "timeout"}, "self-check timeout; request allowed")
        sc._record_span("input", {"zelkor.guardrail.status": "ok"})
    finally:
        ot.get_tracer = orig
    bad, good = exporter.get_finished_spans()
    assert (bad.status.status_code, bad.status.description) == (StatusCode.ERROR, "self-check timeout; request allowed")
    assert good.status.status_code is StatusCode.UNSET


def test_result_lands_on_the_request_span_and_the_check_model_call():
    """NeMo emits ``self_check_input <model>`` after the check; it must carry the result too."""
    import opentelemetry.trace as ot
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.trace import StatusCode

    provider = TracerProvider()
    tracer = provider.get_tracer("t")
    orig = ot.get_tracer
    ot.get_tracer = lambda *_a, **_k: tracer
    try:
        with tracer.start_as_current_span("POST /v1/chat/completions") as request:
            _run('{"block": false}', delay=0.2, timeout_ms=50, mode="log")
            with tracer.start_as_current_span("self_check_input gpt-oss:20b") as gen:
                sc.stamp_check_generation(gen)
            with tracer.start_as_current_span("general gpt-oss:20b") as other:
                sc.stamp_check_generation(other)
    finally:
        ot.get_tracer = orig
    assert request.attributes["zelkor.guardrail.input.mode"] == "log"
    assert request.attributes["langfuse.observation.metadata.guardrail_input_status"] == "timeout"
    assert gen.attributes["zelkor.guardrail.status"] == "timeout"
    assert gen.attributes["langfuse.observation.metadata.guardrail_mode"] == "log"
    assert (gen.status.status_code, gen.status.description) == (StatusCode.ERROR, "self-check timeout; request allowed")
    assert "zelkor.guardrail.status" not in other.attributes
    assert request.status.status_code is StatusCode.UNSET
