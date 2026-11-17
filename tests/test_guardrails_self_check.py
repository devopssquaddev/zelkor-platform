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


def _run(answer=None, delay=0.0, error=None, mode="block", timeout_ms=1500):
    async def fake_task(**_):
        if delay:
            await asyncio.sleep(delay)
        if error:
            raise error
        return True, answer

    return asyncio.run(sc.check(side="input", mode=mode, timeout_ms=timeout_ms,
                                text="some text", run_task=fake_task))


def test_block_mode_refuses_on_a_block_verdict():
    assert _run('{"block": true}')["blocked"] is True


def test_log_mode_never_refuses():
    verdict = _run('{"block": true}', mode="log")
    assert verdict == {"blocked": False, "verdict": "block", "status": "ok"}


def test_unclear_answer_lets_the_request_through():
    assert _run("Yes")["blocked"] is False
    assert _run("Yes")["status"] == "unparseable"


def test_timeout_lets_the_request_through():
    verdict = _run('{"block": true}', delay=0.2, timeout_ms=50)
    assert verdict["blocked"] is False and verdict["status"] == "unavailable"


def test_backend_error_lets_the_request_through():
    assert _run(error=RuntimeError("502"))["status"] == "unavailable"


def test_empty_text_is_not_checked():
    async def never(**_):
        raise AssertionError("called")

    verdict = asyncio.run(sc.check(side="input", mode="block", timeout_ms=100, text="", run_task=never))
    assert verdict["blocked"] is False and verdict["status"] == "skipped"
