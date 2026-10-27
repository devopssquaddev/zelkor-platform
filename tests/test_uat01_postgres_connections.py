"""UAT-01 (production profile): Postgres has room for autoscaled clients (live; needs KUBECONTEXT).

Skips unless the CNPG Cluster exists (operator-cr). ``ZELKOR_MIN_PG_CONNECTIONS`` (default 300)
is the production-profile floor; kind and quickstart keep the operator default.
"""
from __future__ import annotations

import json
import os

import pytest

from tests.helpers.kube import kubectl_run
from tests.helpers.runtime_agents import require_kube

REL = os.environ.get("ZELKOR_PLATFORM_RELEASE", "zelkor-platform")
FLOOR = int(os.environ.get("ZELKOR_MIN_PG_CONNECTIONS", "300"))


def _primary() -> str:
    proc = kubectl_run(["get", f"cluster.postgresql.cnpg.io/{REL}-postgresql", "-o", "json"])
    if proc.returncode != 0:
        pytest.skip("no CNPG Cluster (not operator-cr)")
    return json.loads(proc.stdout)["status"]["currentPrimary"]


def test_uat01_postgres_max_connections_meets_production_floor():
    require_kube()
    pod = _primary()
    proc = kubectl_run(["exec", pod, "-c", "postgres", "--", "psql", "-U", "postgres", "-tAc", "show max_connections"])
    assert proc.returncode == 0, proc.stderr
    assert int(proc.stdout.strip()) >= FLOOR


def test_uat01_no_connection_slot_exhaustion_logged():
    require_kube()
    pod = _primary()
    since = os.environ.get("ZELKOR_PG_LOG_WINDOW", "60m")
    proc = kubectl_run(["logs", pod, "-c", "postgres", f"--since={since}"], timeout=90)
    assert "remaining connection slots are reserved" not in proc.stdout
