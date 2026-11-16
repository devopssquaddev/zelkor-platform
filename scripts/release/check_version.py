#!/usr/bin/env python3
"""CE-19b source-tag check: tag vX.Y.Z-ce == every Chart.yaml version/appVersion == every
first-party image tag (chart and example values, Zelkor FROM/ARG bases of released images).

Usage: check_version.py vX.Y.Z-ce [--root DIR] [--github-output FILE]
Exit 1 with one line per mismatch; the release workflow stops before building anything.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

TAG_RE = re.compile(r"^v(\d+\.\d+\.\d+)-ce$")
FIRST_PARTY = "ghcr.io/devopssquaddev/zelkor-"
DOCKER_REF_RE = re.compile(r"ghcr\.io/devopssquaddev/(zelkor-[a-z0-9-]+):([^\s\"'@]+)")


def _charts(root: Path) -> list[Path]:
    return sorted(root.glob("charts/*/Chart.yaml")) + sorted(root.glob("examples/*/chart/Chart.yaml"))


def _values(root: Path) -> list[Path]:
    return (sorted(root.glob("charts/*/values.yaml")) + sorted(root.glob("examples/*/chart/values.yaml"))
            + sorted(root.glob("examples/armored-agents/*/values.yaml")))


def _walk_images(node, path=""):
    if isinstance(node, dict):
        repo = node.get("repository")
        if isinstance(repo, str) and repo.startswith(FIRST_PARTY) and "tag" in node:
            yield path, repo, str(node.get("tag") or "")
        for k, v in node.items():
            yield from _walk_images(v, f"{path}.{k}" if path else str(k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk_images(v, f"{path}[{i}]")


def released_dockerfiles(root: Path) -> list[Path]:
    out = subprocess.run(["bash", str(root / "scripts/build-images.sh"), "--list-json"],
                         capture_output=True, text=True, check=True).stdout
    return [root / p["dockerfile"] for p in json.loads(out)]


def check(root: Path, tag: str) -> tuple[str, list[str]]:
    m = TAG_RE.match(tag)
    if not m:
        return "", [f"tag {tag!r} is not vX.Y.Z-ce"]
    version = m.group(1)
    errors: list[str] = []

    for chart in _charts(root):
        rel = chart.relative_to(root)
        data = yaml.safe_load(chart.read_text()) or {}
        for key in ("version", "appVersion"):
            if str(data.get(key, "")) != version:
                errors.append(f"{rel}: {key} {data.get(key)!r} != {version}")
        for dep in data.get("dependencies") or []:
            if str(dep.get("name", "")).startswith("zelkor-") and str(dep.get("version", "")) != version:
                errors.append(f"{rel}: dependency {dep.get('alias') or dep['name']} {dep.get('version')!r} != {version}")

    for values in _values(root):
        rel = values.relative_to(root)
        for path, repo, img_tag in _walk_images(yaml.safe_load(values.read_text()) or {}):
            if img_tag != version:
                errors.append(f"{rel}: {path} {repo}:{img_tag or '<empty>'} != {version}")

    for df in released_dockerfiles(root):
        rel = df.relative_to(root)
        for lineno, line in enumerate(df.read_text().splitlines(), 1):
            if not line.lstrip().upper().startswith(("FROM", "ARG")):
                continue
            for name, img_tag in DOCKER_REF_RE.findall(line):
                if img_tag != version:
                    errors.append(f"{rel}:{lineno}: {name}:{img_tag} != {version}")
    return version, errors


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("tag")
    ap.add_argument("--root", default=".")
    ap.add_argument("--github-output", default="")
    args = ap.parse_args(argv)
    version, errors = check(Path(args.root).resolve(), args.tag)
    for e in errors:
        print(f"source-tag mismatch: {e}", file=sys.stderr)
    if errors:
        return 1
    if args.github_output:
        with open(args.github_output, "a", encoding="utf-8") as f:
            f.write(f"version={version}\n")
    print(f"{args.tag}: charts and first-party image tags are {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
