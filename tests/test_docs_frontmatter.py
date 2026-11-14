"""Docs frontmatter contract: search snippets, the site sidebar and llms.txt read these fields."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

DOCS = Path(__file__).resolve().parents[1] / "docs"
PAGES = sorted(p for p in DOCS.rglob("*.md") if "public" not in p.relative_to(DOCS).parts)

ALLOWED = {
    "type": {"tutorial", "how-to", "reference", "explanation", "kb"},
    "audience": {"human", "agent", "both"},
    "edition": {"ce", "pro", "enterprise", "all"},
}
REQUIRED = ("title", "description", "type", "sidebar_group", "audience", "edition")


def _frontmatter(page: Path) -> tuple[dict, str]:
    text = page.read_text()
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    assert m, f"{page.relative_to(DOCS)}: no YAML frontmatter"
    return yaml.safe_load(m.group(1)) or {}, m.group(2)


@pytest.mark.parametrize("page", PAGES, ids=lambda p: str(p.relative_to(DOCS)))
def test_frontmatter_fields(page: Path):
    data, body = _frontmatter(page)
    missing = [k for k in REQUIRED if not data.get(k)]
    assert not missing, f"missing {missing}"
    assert len(str(data["description"])) <= 160, "description over 160 chars"
    for key, allowed in ALLOWED.items():
        assert data[key] in allowed, f"{key}={data[key]!r} not in {sorted(allowed)}"
    prose = re.sub(r"^```.*?^```", "", body, flags=re.S | re.M)
    h1 = [line for line in prose.splitlines() if line.startswith("# ")]
    assert len(h1) == 1, f"expected one H1, found {h1}"
    assert str(data["title"]) == h1[0][2:].replace("`", "").strip(), "title must match the H1"
