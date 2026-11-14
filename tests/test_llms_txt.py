"""GEO: llms.txt / llms-full.txt are generated from docs/ frontmatter and stay small and complete."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WEBSITE = ROOT / "website"
DOCS = ROOT / "docs"
LENS_PAGES = (
    "agent-deploy.md",
    "architecture.md",
    "architecture-request-path.md",
    "architecture-sandbox.md",
    "architecture-trace.md",
    "architecture-tenants.md",
)


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> Path:
    node = shutil.which("node", path=os.environ.get("ZELKOR_NODE_PATH") or os.environ.get("PATH"))
    if not node or not (WEBSITE / "node_modules" / "gray-matter").is_dir():
        pytest.skip("node + website/node_modules required (cd website && npm ci)")
    out = tmp_path_factory.mktemp("llms")
    r = subprocess.run(
        [node, "scripts/build-llms.mjs", "--out", str(out)],
        cwd=WEBSITE, capture_output=True, text=True, check=False,
    )
    assert r.returncode == 0, r.stderr
    return out


def test_index_under_token_budget(built: Path):
    assert len((built / "llms.txt").read_text()) / 4 <= 2000


def test_index_structure(built: Path):
    text = (built / "llms.txt").read_text()
    assert text.startswith("# Zelkor\n\n> ")
    assert "./install.sh" in text and "zelkor deploy -f" in text
    assert "{{" not in text


def _index_entries(built: Path) -> str:
    return "\n".join(l for l in (built / "llms.txt").read_text().splitlines() if l.startswith("- ["))


def test_every_page_listed_once_and_served_as_markdown(built: Path):
    text = _index_entries(built)
    pages = [p.relative_to(DOCS).as_posix() for p in DOCS.rglob("*.md")
             if "public" not in p.relative_to(DOCS).parts and p.name != "README.md"]
    for rel in pages:
        n = len(re.findall(rf"\]\(https://docs\.zelkor\.io/{re.escape(rel)}\)", text))
        assert n == 1, f"{rel} listed {n} times"
        assert (built / rel).is_file(), f"{rel}.md not emitted"


def test_lens_pages_carry_query_note(built: Path):
    text = _index_entries(built)
    for rel in LENS_PAGES:
        line = next(l for l in text.splitlines() if f"docs.zelkor.io/{rel})" in l)
        description = yaml.safe_load((DOCS / rel).read_text().split("---")[1])["description"]
        assert line.split("): ", 1)[1] != description, f"{rel}: note must be the query phrase"


def test_full_has_every_page_without_frontmatter_or_markers(built: Path):
    full = (built / "llms-full.txt").read_text()
    assert "\nsidebar_group:" not in full
    assert "zelkor-proof" not in full
    assert full.count("\nSource: https://docs.zelkor.io/") + full.startswith("Source") >= 40
