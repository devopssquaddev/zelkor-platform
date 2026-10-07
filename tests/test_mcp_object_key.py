"""Key prefix rules for the object MCP. No cluster and no bucket."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mcp"))

from common.tenant import normalize_key, strip_tenant, tenant_key  # noqa: E402


def test_normalize_key_collapses_separators():
    assert normalize_key("a//b///c") == "a/b/c"
    assert normalize_key("reports/2026/q1.txt") == "reports/2026/q1.txt"


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "..",
        "../secret",
        "a/../b",
        "/abs",
        "a\\b",
        "a\x00b",
        "a\nb",
        "///",
        "a/" + ("b" * 1024),
    ],
)
def test_normalize_key_rejects(raw):
    with pytest.raises(PermissionError):
        normalize_key(raw)


def test_tenant_key_prefixes_and_strips():
    assert tenant_key("tenant-a", "reports/q1.txt") == "tenant-a/reports/q1.txt"
    assert strip_tenant("tenant-a", "tenant-a/reports/q1.txt") == "reports/q1.txt"
    assert strip_tenant("tenant-a", tenant_key("tenant-a", "a//b")) == "a/b"


def test_strip_tenant_rejects_other_tenants_and_traversal():
    with pytest.raises(PermissionError):
        strip_tenant("tenant-b", "tenant-a/reports/q1.txt")
    with pytest.raises(PermissionError):
        strip_tenant("tenant-a", "tenant-a/../tenant-b/secret")
    with pytest.raises(PermissionError):
        tenant_key("tenant-a", "/tenant-b/secret")
    with pytest.raises(PermissionError):
        tenant_key("tenant-a", "../tenant-b/secret")
    with pytest.raises(PermissionError):
        tenant_key("bad/tenant", "ok")
