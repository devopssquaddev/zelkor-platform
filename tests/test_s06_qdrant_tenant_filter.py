"""S-06 (P6) L1: the Qdrant wrap keeps every read and write in the caller's tenant without a live
embedder. The upsert stamp overrides a forged tenant, the store query filters on the caller,
point and entry payloads of other tenants are dropped, and search post-filters whatever the
store returns. The live upsert-then-search case needs an embeddings route (S-gate lab)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

import wrappers.qdrant_server as q


def test_s06_upsert_stamp_overrides_forged_tenant():
    p = q.stamp_upsert_payload({"tenant_id": "tenant_b", "k": "v"}, "doc", "tenant_a")
    assert p["tenant_id"] == "tenant_a" and p["k"] == "v"


def test_s06_store_filter_is_the_callers_tenant():
    models = pytest.importorskip("qdrant_client.models")
    filt = q._tenant_filter(models, "tenant_a")
    (cond,) = filt.must
    assert cond.key == "tenant_id" and cond.match.value == "tenant_a"


def test_s06_point_payloads_of_other_tenants_are_dropped():
    points = [{"payload": {"tenant_id": "tenant_a", "document": "mine"}},
              {"payload": {"tenant_id": "tenant_b", "document": "theirs"}},
              {"payload": {"metadata": {"tenant_id": "tenant_b"}, "document": "nested theirs"}},
              {"payload": {"metadata": {"tenant_id": "tenant_a"}, "document": "nested mine"}},
              {"payload": {"document": "no tenant"}}]
    assert [d["document"] for d in q._payloads_from_points(points, "tenant_a")] == ["mine", "nested mine"]


def test_s06_entry_payloads_of_other_tenants_are_dropped():
    entries = [SimpleNamespace(content="mine", metadata={"tenant_id": "tenant_a"}),
               SimpleNamespace(content="theirs", metadata={"tenant_id": "tenant_b"}),
               SimpleNamespace(content="untagged", metadata={})]
    assert [d["document"] for d in q._payloads_from_entries(entries, "tenant_a")] == ["mine"]


@pytest.mark.parametrize("path", ["connector", "scroll"])
def test_s06_search_post_filters_whatever_the_store_returns(monkeypatch, path):
    leaky = [{"tenant_id": "tenant_a", "document": "mine"}, {"tenant_id": "tenant_b", "document": "theirs"}]
    monkeypatch.setattr(q, "_search_with_connector", lambda *a: leaky if path == "connector" else None)
    monkeypatch.setattr(q, "_scroll_tenant", lambda *a: leaky)
    out = q.QdrantMCPServer().call_tool("search_documents", {"query": "x", "limit": 5}, "tenant_a")
    assert [d["document"] for d in out["documents"]] == ["mine"]
