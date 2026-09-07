"""Sync coroutine runner used when MCP tools load during uvicorn lifespan."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "images" / "aegra"))

from mcp_inject import _run_coro_sync  # noqa: E402


async def _answer():
    return 42


def test_run_coro_sync_without_running_loop():
    assert _run_coro_sync(_answer()) == 42


def test_run_coro_sync_with_running_loop():
    async def _inside_loop():
        return _run_coro_sync(_answer())

    assert asyncio.run(_inside_loop()) == 42
