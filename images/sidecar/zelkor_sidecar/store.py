"""Tenant-scoped thread/run/message/event store for the sidecar (CE-14).

Every read and write takes (tenant_id, graph_id). A thread owned by another tenant or
graph is indistinguishable from a missing one (callers return 404). ``MemoryStore`` backs
unit tests; ``PgStore`` is the production store (platform Postgres, ``zelkor_*`` tables).
"""
from __future__ import annotations

import asyncio
import copy
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

RUN_STATUSES = ("pending", "running", "success", "error", "timeout", "interrupted")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso(value: Any) -> str:
    return value.isoformat() if isinstance(value, datetime) else str(value)


def _matches(metadata: Dict[str, Any], query: Dict[str, Any]) -> bool:
    return all(metadata.get(k) == v for k, v in (query or {}).items())


class Store:
    """Interface. All methods are tenant- and graph-scoped."""

    async def create_thread(self, tenant_id: str, graph_id: str, metadata: Optional[dict] = None,
                            thread_id: Optional[str] = None) -> dict:
        raise NotImplementedError

    async def get_thread(self, tenant_id: str, graph_id: str, thread_id: str) -> Optional[dict]:
        raise NotImplementedError

    async def search_threads(self, tenant_id: str, graph_id: str, metadata: Optional[dict] = None,
                             limit: int = 10, offset: int = 0) -> List[dict]:
        raise NotImplementedError

    async def set_thread(self, tenant_id: str, graph_id: str, thread_id: str, *,
                         status: Optional[str] = None,
                         runtime_session_id: Optional[str] = None) -> None:
        raise NotImplementedError

    async def list_messages(self, tenant_id: str, graph_id: str, thread_id: str) -> List[dict]:
        raise NotImplementedError

    async def append_messages(self, tenant_id: str, graph_id: str, thread_id: str,
                              run_id: Optional[str], messages: List[dict]) -> None:
        raise NotImplementedError

    async def create_run(self, tenant_id: str, graph_id: str, thread_id: str) -> dict:
        raise NotImplementedError

    async def get_run(self, tenant_id: str, graph_id: str, run_id: str) -> Optional[dict]:
        raise NotImplementedError

    async def update_run(self, run_id: str, *, status: str, error: Optional[str] = None,
                         runtime_run_id: Optional[str] = None) -> None:
        raise NotImplementedError

    async def add_event(self, run_id: str, event_key: str, event: str, data: Any) -> bool:
        """Persist one run event; False when (run_id, event_key) was already stored."""
        raise NotImplementedError

    async def list_events(self, run_id: str) -> List[dict]:
        raise NotImplementedError

    async def close(self) -> None:
        return None


class MemoryStore(Store):
    def __init__(self) -> None:
        self._threads: Dict[str, dict] = {}
        self._messages: Dict[str, List[dict]] = {}
        self._runs: Dict[str, dict] = {}
        self._events: Dict[str, List[dict]] = {}
        self._seq = 0
        self._lock = asyncio.Lock()

    def _owned(self, tenant_id: str, graph_id: str, thread_id: str) -> Optional[dict]:
        row = self._threads.get(str(thread_id))
        if row and row["tenant_id"] == tenant_id and row["graph_id"] == graph_id:
            return row
        return None

    @staticmethod
    def _public(row: dict) -> dict:
        out = {k: copy.deepcopy(v) for k, v in row.items() if k not in ("tenant_id", "graph_id")}
        return out

    async def create_thread(self, tenant_id, graph_id, metadata=None, thread_id=None):
        tid = str(thread_id or uuid.uuid4())
        if tid in self._threads:
            if self._owned(tenant_id, graph_id, tid) is None:
                raise PermissionError("thread id already in use")
            return self._public(self._threads[tid])
        ts = now_iso()
        row = {"thread_id": tid, "tenant_id": tenant_id, "graph_id": graph_id,
               "metadata": dict(metadata or {}), "status": "idle", "runtime_session_id": None,
               "created_at": ts, "updated_at": ts}
        self._threads[tid] = row
        self._messages[tid] = []
        return self._public(row)

    async def get_thread(self, tenant_id, graph_id, thread_id):
        row = self._owned(tenant_id, graph_id, thread_id)
        return self._public(row) if row else None

    async def search_threads(self, tenant_id, graph_id, metadata=None, limit=10, offset=0):
        rows = [r for r in self._threads.values()
                if r["tenant_id"] == tenant_id and r["graph_id"] == graph_id
                and _matches(r["metadata"], metadata or {})]
        rows.sort(key=lambda r: r["created_at"], reverse=True)
        return [self._public(r) for r in rows[offset: offset + limit]]

    async def set_thread(self, tenant_id, graph_id, thread_id, *, status=None, runtime_session_id=None):
        row = self._owned(tenant_id, graph_id, thread_id)
        if row is None:
            raise KeyError(thread_id)
        if status is not None:
            row["status"] = status
        if runtime_session_id is not None:
            row["runtime_session_id"] = runtime_session_id
        row["updated_at"] = now_iso()

    async def list_messages(self, tenant_id, graph_id, thread_id):
        if self._owned(tenant_id, graph_id, thread_id) is None:
            return []
        return copy.deepcopy(self._messages.get(str(thread_id), []))

    async def append_messages(self, tenant_id, graph_id, thread_id, run_id, messages):
        if self._owned(tenant_id, graph_id, thread_id) is None:
            raise KeyError(thread_id)
        self._messages[str(thread_id)].extend(copy.deepcopy(messages))

    async def create_run(self, tenant_id, graph_id, thread_id):
        if self._owned(tenant_id, graph_id, thread_id) is None:
            raise KeyError(thread_id)
        ts = now_iso()
        run = {"run_id": str(uuid.uuid4()), "thread_id": str(thread_id), "tenant_id": tenant_id,
               "graph_id": graph_id, "assistant_id": graph_id, "status": "pending", "error": None,
               "runtime_run_id": None, "created_at": ts, "updated_at": ts}
        self._runs[run["run_id"]] = run
        self._events[run["run_id"]] = []
        return self._public(run)

    async def get_run(self, tenant_id, graph_id, run_id):
        run = self._runs.get(str(run_id))
        if run and run["tenant_id"] == tenant_id and run["graph_id"] == graph_id:
            return self._public(run)
        return None

    async def update_run(self, run_id, *, status, error=None, runtime_run_id=None):
        if status not in RUN_STATUSES:
            raise ValueError(status)
        run = self._runs[str(run_id)]
        run["status"] = status
        if error is not None:
            run["error"] = error
        if runtime_run_id is not None:
            run["runtime_run_id"] = runtime_run_id
        run["updated_at"] = now_iso()

    async def add_event(self, run_id, event_key, event, data):
        async with self._lock:
            events = self._events.setdefault(str(run_id), [])
            if any(e["event_key"] == event_key for e in events):
                return False
            self._seq += 1
            events.append({"seq": self._seq, "event_key": event_key, "event": event,
                           "data": copy.deepcopy(data)})
            return True

    async def list_events(self, run_id):
        return copy.deepcopy(self._events.get(str(run_id), []))


class PgStore(Store):
    """Postgres store (psycopg 3 async pool). Schema: ``migrations/*.sql`` via ``migrate``."""

    def __init__(self, dsn: str, *, min_size: int = 1, max_size: int = 5) -> None:
        from psycopg_pool import AsyncConnectionPool

        self._pool = AsyncConnectionPool(dsn, min_size=min_size, max_size=max_size, open=False)

    async def open(self) -> None:
        await self._pool.open(wait=True)

    async def close(self) -> None:
        await self._pool.close()

    async def _fetch(self, sql: str, params: tuple) -> List[dict]:
        from psycopg.rows import dict_row

        async with self._pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(sql, params)
                return list(await cur.fetchall()) if cur.description else []

    async def _exec(self, sql: str, params: tuple) -> int:
        async with self._pool.connection() as conn:
            cur = await conn.execute(sql, params)
            return cur.rowcount

    @staticmethod
    def _thread(row: dict) -> dict:
        return {"thread_id": str(row["thread_id"]), "metadata": row["metadata"] or {},
                "status": row["status"], "runtime_session_id": row["runtime_session_id"],
                "created_at": _iso(row["created_at"]), "updated_at": _iso(row["updated_at"])}

    @staticmethod
    def _run(row: dict) -> dict:
        return {"run_id": str(row["run_id"]), "thread_id": str(row["thread_id"]),
                "assistant_id": row["graph_id"], "status": row["status"], "error": row["error"],
                "runtime_run_id": row["runtime_run_id"],
                "created_at": _iso(row["created_at"]), "updated_at": _iso(row["updated_at"])}

    async def create_thread(self, tenant_id, graph_id, metadata=None, thread_id=None):
        tid = str(thread_id or uuid.uuid4())
        rows = await self._fetch(
            "INSERT INTO zelkor_threads (thread_id, tenant_id, graph_id, metadata) "
            "VALUES (%s, %s, %s, %s::jsonb) ON CONFLICT (thread_id) DO NOTHING RETURNING *",
            (tid, tenant_id, graph_id, json.dumps(metadata or {})),
        )
        if rows:
            return self._thread(rows[0])
        existing = await self.get_thread(tenant_id, graph_id, tid)
        if existing is None:
            raise PermissionError("thread id already in use")
        return existing

    async def get_thread(self, tenant_id, graph_id, thread_id):
        rows = await self._fetch(
            "SELECT * FROM zelkor_threads WHERE thread_id = %s AND tenant_id = %s AND graph_id = %s",
            (str(thread_id), tenant_id, graph_id),
        )
        return self._thread(rows[0]) if rows else None

    async def search_threads(self, tenant_id, graph_id, metadata=None, limit=10, offset=0):
        rows = await self._fetch(
            "SELECT * FROM zelkor_threads WHERE tenant_id = %s AND graph_id = %s "
            "AND metadata @> %s::jsonb ORDER BY created_at DESC LIMIT %s OFFSET %s",
            (tenant_id, graph_id, json.dumps(metadata or {}), int(limit), int(offset)),
        )
        return [self._thread(r) for r in rows]

    async def set_thread(self, tenant_id, graph_id, thread_id, *, status=None, runtime_session_id=None):
        count = await self._exec(
            "UPDATE zelkor_threads SET status = COALESCE(%s, status), "
            "runtime_session_id = COALESCE(%s, runtime_session_id), updated_at = now() "
            "WHERE thread_id = %s AND tenant_id = %s AND graph_id = %s",
            (status, runtime_session_id, str(thread_id), tenant_id, graph_id),
        )
        if count == 0:
            raise KeyError(thread_id)

    async def list_messages(self, tenant_id, graph_id, thread_id):
        rows = await self._fetch(
            "SELECT m.message FROM zelkor_messages m JOIN zelkor_threads t USING (thread_id) "
            "WHERE m.thread_id = %s AND t.tenant_id = %s AND t.graph_id = %s ORDER BY m.seq",
            (str(thread_id), tenant_id, graph_id),
        )
        return [r["message"] for r in rows]

    async def append_messages(self, tenant_id, graph_id, thread_id, run_id, messages):
        if await self.get_thread(tenant_id, graph_id, thread_id) is None:
            raise KeyError(thread_id)
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.executemany(
                    "INSERT INTO zelkor_messages (thread_id, run_id, message) VALUES (%s, %s, %s::jsonb)",
                    [(str(thread_id), run_id, json.dumps(m)) for m in messages],
                )

    async def create_run(self, tenant_id, graph_id, thread_id):
        if await self.get_thread(tenant_id, graph_id, thread_id) is None:
            raise KeyError(thread_id)
        rows = await self._fetch(
            "INSERT INTO zelkor_runs (run_id, thread_id, tenant_id, graph_id) "
            "VALUES (%s, %s, %s, %s) RETURNING *",
            (str(uuid.uuid4()), str(thread_id), tenant_id, graph_id),
        )
        return self._run(rows[0])

    async def get_run(self, tenant_id, graph_id, run_id):
        rows = await self._fetch(
            "SELECT * FROM zelkor_runs WHERE run_id = %s AND tenant_id = %s AND graph_id = %s",
            (str(run_id), tenant_id, graph_id),
        )
        return self._run(rows[0]) if rows else None

    async def update_run(self, run_id, *, status, error=None, runtime_run_id=None):
        if status not in RUN_STATUSES:
            raise ValueError(status)
        await self._exec(
            "UPDATE zelkor_runs SET status = %s, error = COALESCE(%s, error), "
            "runtime_run_id = COALESCE(%s, runtime_run_id), updated_at = now() WHERE run_id = %s",
            (status, error, runtime_run_id, str(run_id)),
        )

    async def add_event(self, run_id, event_key, event, data):
        count = await self._exec(
            "INSERT INTO zelkor_run_events (run_id, event_key, event, data) "
            "VALUES (%s, %s, %s, %s::jsonb) ON CONFLICT (run_id, event_key) DO NOTHING",
            (str(run_id), event_key, event, json.dumps(data)),
        )
        return count == 1

    async def list_events(self, run_id):
        rows = await self._fetch(
            "SELECT seq, event_key, event, data FROM zelkor_run_events WHERE run_id = %s ORDER BY seq",
            (str(run_id),),
        )
        return rows
