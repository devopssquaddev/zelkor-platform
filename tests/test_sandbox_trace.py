"""CE-13: sandbox TOOL stamp reads the execution report from LangChain MCP wrappers."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "images" / "aegra"))

from sandbox_trace import _coerce_execution  # noqa: E402

DENIED = {
    "ok": False,
    "execution": {
        "outcome": "denied",
        "violation": "permission_denied_mknod",
        "code_sha": "abc123",
    },
}
TEXT = json.dumps(DENIED)


def _assert_denied(execution):
    assert execution is not None
    assert execution["outcome"] == "denied"
    assert execution["violation"] == "permission_denied_mknod"


def test_dict_and_json_string_still_parse():
    _assert_denied(_coerce_execution(DENIED))
    _assert_denied(_coerce_execution(TEXT))


def test_langchain_list_of_text_blocks():
    _assert_denied(_coerce_execution([{"type": "text", "text": TEXT}]))


def test_content_wrapper_dict():
    _assert_denied(_coerce_execution({"content": [{"type": "text", "text": TEXT}]}))


def test_text_content_objects():
    _assert_denied(_coerce_execution([SimpleNamespace(type="text", text=TEXT)]))


def test_report_in_a_later_block():
    blocks = [{"type": "text", "text": "stdout: hello"}, {"type": "text", "text": TEXT}]
    _assert_denied(_coerce_execution(blocks))


def test_non_report_inputs_return_none():
    assert _coerce_execution([{"type": "text", "text": "plain output"}]) is None
    assert _coerce_execution([{"type": "image", "data": "..."}]) is None
    assert _coerce_execution({"content": "not a list"}) is None
    assert _coerce_execution([]) is None
    assert _coerce_execution(None) is None
