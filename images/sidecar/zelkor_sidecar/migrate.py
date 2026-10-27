"""Apply sidecar schema migrations (init container: ``python -m zelkor_sidecar.migrate``).

Numbered ``migrations/NNN_*.sql`` files run once each, in order, inside one transaction
per file. A Postgres advisory lock serialises concurrent agent pods starting together.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import List, Tuple

logger = logging.getLogger("zelkor-sidecar")

MIGRATIONS = Path(__file__).resolve().parent / "migrations"
LOCK_KEY = 7_331_014  # arbitrary, stable: "CE-14"


def pending(applied: set[int], available: List[Tuple[int, Path]]) -> List[Tuple[int, Path]]:
    return [(v, p) for v, p in available if v not in applied]


def available_migrations(root: Path = MIGRATIONS) -> List[Tuple[int, Path]]:
    out = []
    for path in sorted(root.glob("*.sql")):
        head = path.name.split("_", 1)[0]
        if head.isdigit():
            out.append((int(head), path))
    versions = [v for v, _ in out]
    if len(versions) != len(set(versions)):
        raise RuntimeError("duplicate migration version")
    return out


def run(dsn: str) -> int:
    import psycopg

    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute("SELECT pg_advisory_lock(%s)", (LOCK_KEY,))
        try:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS zelkor_sidecar_schema "
                "(version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
            )
            applied = {r[0] for r in conn.execute("SELECT version FROM zelkor_sidecar_schema").fetchall()}
            todo = pending(applied, available_migrations())
            for version, path in todo:
                with conn.transaction():
                    conn.execute(path.read_text(encoding="utf-8"))
                    conn.execute(
                        "INSERT INTO zelkor_sidecar_schema (version, name) VALUES (%s, %s)",
                        (version, path.name),
                    )
                logger.info("migration applied", extra={"event": "migrate", "status": path.name})
            if not todo:
                logger.info("schema up to date", extra={"event": "migrate", "status": "noop"})
            return len(todo)
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))


def main() -> int:
    try:
        from zelkor_logging import configure_logging

        configure_logging("zelkor-sidecar")
    except ImportError:
        logging.basicConfig(level=os.getenv("ZELKOR_LOG_LEVEL", "INFO"))
    dsn = os.getenv("DATABASE_URL", "").strip()
    if not dsn:
        logger.error("DATABASE_URL is required for migrate")
        return 2
    run(dsn)
    return 0


if __name__ == "__main__":
    sys.exit(main())
