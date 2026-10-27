"""CE-14 sidecar PgStore against a real Postgres. Skips unless ZELKOR_SIDECAR_TEST_DSN is set."""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "images" / "sidecar"))

DSN = os.environ.get("ZELKOR_SIDECAR_TEST_DSN", "").strip()
pytestmark = pytest.mark.skipif(not DSN, reason="ZELKOR_SIDECAR_TEST_DSN not set")


def _run(coro):
    return asyncio.run(coro)


def test_migrate_is_idempotent():
    pytest.importorskip("psycopg")
    from zelkor_sidecar.migrate import run

    run(DSN)
    assert run(DSN) == 0


def test_pgstore_tenant_scoping_and_events():
    pytest.importorskip("psycopg_pool")
    from zelkor_sidecar.migrate import run
    from zelkor_sidecar.store import PgStore

    run(DSN)

    async def go():
        store = PgStore(DSN)
        await store.open()
        try:
            t = await store.create_thread("tenant-a", "desk", {"tag": "pg"})
            tid = t["thread_id"]
            assert await store.get_thread("tenant-b", "desk", tid) is None
            assert await store.get_thread("tenant-a", "other-graph", tid) is None
            with pytest.raises(PermissionError):
                await store.create_thread("tenant-b", "desk", {}, tid)
            hits = await store.search_threads("tenant-a", "desk", {"tag": "pg"}, limit=50)
            assert tid in [h["thread_id"] for h in hits]
            assert tid not in [h["thread_id"] for h in await store.search_threads("tenant-b", "desk", {"tag": "pg"})]

            run_ = await store.create_run("tenant-a", "desk", tid)
            await store.append_messages("tenant-a", "desk", tid, run_["run_id"],
                                        [{"type": "human", "content": "hi", "id": "m1"}])
            assert await store.list_messages("tenant-b", "desk", tid) == []
            assert [m["id"] for m in await store.list_messages("tenant-a", "desk", tid)] == ["m1"]
            with pytest.raises(KeyError):
                await store.append_messages("tenant-b", "desk", tid, None, [{"type": "human"}])

            assert await store.add_event(run_["run_id"], "k1", "custom", {"a": 1}) is True
            assert await store.add_event(run_["run_id"], "k1", "custom", {"a": 1}) is False
            await store.update_run(run_["run_id"], status="success")
            assert (await store.get_run("tenant-a", "desk", run_["run_id"]))["status"] == "success"
            assert await store.get_run("tenant-b", "desk", run_["run_id"]) is None

            await store.set_thread("tenant-a", "desk", tid, runtime_session_id="ses-1")
            assert (await store.get_thread("tenant-a", "desk", tid))["runtime_session_id"] == "ses-1"
            with pytest.raises(KeyError):
                await store.set_thread("tenant-b", "desk", tid, status="busy")
        finally:
            await store.close()

    _run(go())
