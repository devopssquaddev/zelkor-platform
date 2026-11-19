"""in-cluster-basic Postgres keeps its data on a PVC by default (an emptyDir lost every thread, run
and role on a pod restart); persistence.enabled=false keeps the emptyDir."""
from __future__ import annotations

import yaml

from tests.test_helm_values_schema import _helm


def _sts(*extra: str) -> dict:
    r = _helm(*extra)
    assert r.returncode == 0, r.stderr[-400:]
    return next(d for d in yaml.safe_load_all(r.stdout)
                if d and d["kind"] == "StatefulSet" and d["metadata"]["name"].endswith("-postgresql"))


def test_postgres_data_is_a_pvc_by_default():
    sts = _sts()
    (vct,) = sts["spec"]["volumeClaimTemplates"]
    assert vct["metadata"]["name"] == "data"
    assert vct["spec"]["resources"]["requests"]["storage"] == "8Gi"
    assert "data" not in {v["name"] for v in sts["spec"]["template"]["spec"]["volumes"]}
    mounts = {m["name"]: m["mountPath"] for c in sts["spec"]["template"]["spec"]["containers"] for m in c["volumeMounts"]}
    assert mounts["data"] == "/var/lib/postgresql"


def test_postgres_storage_class_and_size():
    (vct,) = _sts("--set", "postgresql.persistence.size=20Gi",
                  "--set", "postgresql.persistence.storageClass=fast")["spec"]["volumeClaimTemplates"]
    assert vct["spec"]["resources"]["requests"]["storage"] == "20Gi"
    assert vct["spec"]["storageClassName"] == "fast"


def test_postgres_persistence_off_is_an_emptydir():
    sts = _sts("--set", "postgresql.persistence.enabled=false")
    assert not sts["spec"].get("volumeClaimTemplates")
    vols = {v["name"]: v for v in sts["spec"]["template"]["spec"]["volumes"]}
    assert vols["data"] == {"name": "data", "emptyDir": {}}
