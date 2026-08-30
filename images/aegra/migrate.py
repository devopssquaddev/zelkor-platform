"""Out-of-band Aegra Alembic upgrade (Helm Job / init). Not the FastAPI lifespan path."""
from __future__ import annotations

from aegra_api.core.migrations import run_migrations


def main() -> None:
    run_migrations()


if __name__ == "__main__":
    main()
