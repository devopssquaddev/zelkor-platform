"""C12: dev auth knobs and env vars must not appear in shipped chart/agent surfaces."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SCAN_ROOTS = [
    ROOT / "charts",
    ROOT / "profiles",
    ROOT / "agents",
    ROOT / "images",
    ROOT / "mcp",
    ROOT / "cli" / "src",
]

FORBIDDEN = re.compile(
    r"AUTH_DEV_|AUTH_TRUST_TENANT_HEADER|AUTH_JWT_SECRET|"
    r"devTokens|trustTenantHeader|jwtSecret|Bearer dev:|ZELKOR_TENANT_HEADER"
)


def test_no_dev_auth_literals_in_shipped_trees():
    hits: list[str] = []
    for base in SCAN_ROOTS:
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix not in {".yaml", ".yml", ".tpl", ".py", ".md", ".sh"}:
                continue
            if "test" in path.parts and path.suffix == ".py":
                continue
            if path.name in {"values.v1-intent-stubs.yaml", "values.schema.json"}:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for i, line in enumerate(text.splitlines(), 1):
                if FORBIDDEN.search(line):
                    hits.append(f"{path.relative_to(ROOT)}:{i}: {line.strip()[:120]}")
    assert not hits, "forbidden dev-auth literals:\n" + "\n".join(hits[:20])
