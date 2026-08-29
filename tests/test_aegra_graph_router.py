"""Unit tests for the Aegra front-door graph_id catalog (no cluster)."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "images" / "aegra"))

from graph_router import extract_graph_id, load_workers  # noqa: E402


def test_load_workers_catalog():
    catalog = load_workers(
        json.dumps([{"graphId": "fraud", "url": "http://fraud.svc:8000"}])
    )
    assert catalog["fraud"] == "http://fraud.svc:8000"


def test_load_workers_rejects_empty_url():
    with pytest.raises(ValueError, match="graphId"):
        load_workers(json.dumps([{"graphId": "x", "url": ""}]))


def test_extract_graph_id_from_body():
    assert extract_graph_id({"graph_id": "fraud"}, {}) == "fraud"
    assert extract_graph_id({"assistant_id": "hr-policy"}, {}) == "hr-policy"


def test_extract_graph_id_from_query():
    assert extract_graph_id(None, {"graph_id": ["fraud"]}) == "fraud"
