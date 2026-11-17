#!/usr/bin/env python3
"""CE-19c: the upstream images a Zelkor release ships, pinned by registry digest.

Reads every image in charts/*/values.yaml that is not first-party (Langfuse web/worker,
datastores, init/installer images), resolves its digest with `crane digest` (read-only; nothing
is pulled, copied or re-pushed: CE-18a forbids redistributing Langfuse /ee), and writes
upstream-digests.json for the release attestation.

Usage: upstream_digests.py [--root DIR] [--out upstream-digests.json] [--list]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import yaml

FIRST_PARTY = "ghcr.io/devopssquaddev/zelkor-"
STRING_IMAGE_KEYS = {"image", "imageName", "initContainerImage"}
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


@dataclass(frozen=True)
class UpstreamRef:
    ref: str
    source: str


def normalize(ref: str) -> str:
    """Fully qualify a Docker reference (docker.io/library/... for bare names)."""
    first = ref.split("/", 1)[0]
    if "/" not in ref:
        return f"docker.io/library/{ref}"
    if "." in first or ":" in first or first == "localhost":
        return ref
    return f"docker.io/{ref}"


def _walk(node, path):
    if isinstance(node, dict):
        repo, tag = node.get("repository"), node.get("tag")
        if isinstance(repo, str) and repo and tag not in (None, ""):
            yield path, f"{repo}:{tag}"
        for k, v in node.items():
            child = f"{path}.{k}" if path else str(k)
            if k in STRING_IMAGE_KEYS and isinstance(v, str) and ":" in v:
                yield child, v
            else:
                yield from _walk(v, child)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk(v, f"{path}[{i}]")


def upstream_refs(root: Path) -> list[UpstreamRef]:
    seen: dict[str, UpstreamRef] = {}
    for values in sorted(root.glob("charts/*/values.yaml")):
        rel = values.relative_to(root).as_posix()
        for path, raw in _walk(yaml.safe_load(values.read_text()) or {}, ""):
            if raw.startswith(FIRST_PARTY):
                continue
            ref = normalize(raw)
            seen.setdefault(ref, UpstreamRef(ref, f"{rel}:{path}"))
    return sorted(seen.values(), key=lambda r: r.ref)


def crane_digest(ref: str) -> str:
    r = subprocess.run(["crane", "digest", ref], capture_output=True, text=True, check=False)
    if r.returncode != 0:
        raise RuntimeError(f"crane digest {ref}: {r.stderr.strip()}")
    return r.stdout.strip()


def resolve(refs: list[UpstreamRef], resolver: Callable[[str], str] = crane_digest) -> dict:
    images = []
    for r in refs:
        digest = resolver(r.ref)
        if not DIGEST_RE.match(digest):
            raise ValueError(f"{r.ref}: resolver returned {digest!r}, not a sha256 digest")
        images.append({"ref": r.ref, "digest": digest, "source": r.source})
    return {"images": images}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", default="upstream-digests.json")
    ap.add_argument("--list", action="store_true", help="print refs; resolve nothing")
    args = ap.parse_args(argv)
    refs = upstream_refs(Path(args.root).resolve())
    if args.list:
        for r in refs:
            print(f"{r.ref}\t{r.source}")
        return 0
    try:
        doc = resolve(refs)
    except (RuntimeError, ValueError) as exc:
        print(f"upstream_digests: {exc}", file=sys.stderr)
        return 1
    Path(args.out).write_text(json.dumps(doc, indent=2) + "\n")
    print(f"upstream_digests: {len(doc['images'])} image(s) -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
