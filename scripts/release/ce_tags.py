#!/usr/bin/env python3
"""CE-19g: the N-1 release for the upgrade gate (highest vX.Y.Z-ce strictly below the current tag).

Usage: ce_tags.py previous vX.Y.Z-ce   (reads `git tag -l 'v*-ce'`)
"""
from __future__ import annotations

import re
import subprocess
import sys

TAG_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)-ce$")


def _key(tag: str) -> tuple[int, int, int] | None:
    m = TAG_RE.match(tag)
    return tuple(int(x) for x in m.groups()) if m else None  # type: ignore[return-value]


def previous(tags: list[str], current: str) -> str:
    cur = _key(current)
    if cur is None:
        raise ValueError(f"{current!r} is not vX.Y.Z-ce")
    older = sorted((k, t) for t in tags if (k := _key(t)) is not None and k < cur)
    if not older:
        raise ValueError(f"no CE release before {current}")
    return older[-1][1]


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[1] != "previous":
        print(__doc__, file=sys.stderr)
        return 2
    tags = subprocess.run(["git", "tag", "-l", "v*-ce"], capture_output=True, text=True, check=True).stdout.split()
    try:
        print(previous(tags, argv[2]))
    except ValueError as exc:
        print(f"ce_tags: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
