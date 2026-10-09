"""TaskGroup errors returned to the client name the inner failure."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "images" / "aegra"))

from taskgroup_unwrap import public_message, root_cause  # noqa: E402


def test_root_cause_unwraps_nested_taskgroup():
    inner = RuntimeError("model is not configured on this gateway")
    mid = ExceptionGroup("unhandled errors in a TaskGroup", [inner])
    outer = ExceptionGroup("unhandled errors in a TaskGroup", [mid])
    assert root_cause(outer) is inner
    assert public_message(outer) == "model is not configured on this gateway"


def test_public_message_joins_multiple_children():
    group = ExceptionGroup(
        "unhandled errors in a TaskGroup",
        [RuntimeError("mcp 401"), RuntimeError("model_not_found")],
    )
    assert public_message(group) == "mcp 401; model_not_found"
