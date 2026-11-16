#!/usr/bin/env python3
"""CE-19b/c attestation predicates, built from the GitHub Actions environment of release.yml.

  provenance  SLSA v1 predicate naming repository, source tag, commit and workflow
              (cosign attest --type slsaprovenance1). Refuses to run unless GITHUB_REF is the
              tag being released and the workflow is release.yml: a mismatched source fails.
  manifest    Release manifest (predicate type RELEASE_PREDICATE_TYPE): first-party image digests,
              chart digests and the upstream images we ship by digest (CE-19c). Attested on the
              signed platform chart.

Usage:
  release_attest.py provenance --tag vX.Y.Z-ce --artifact REF [--dockerfile PATH] --out FILE
  release_attest.py manifest --tag vX.Y.Z-ce --digests DIR --upstream FILE --charts FILE --out FILE
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

WORKFLOW_PATH = ".github/workflows/release.yml"
BUILD_TYPE = "https://github.com/devopssquaddev/zelkor-platform/release/v1"
RELEASE_PREDICATE_TYPE = "https://zelkor.io/attestations/release/v1"
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class SourceMismatch(RuntimeError):
    pass


def _source(env: Mapping[str, str], tag: str) -> dict[str, str]:
    server = env.get("GITHUB_SERVER_URL", "https://github.com")
    repo = env.get("GITHUB_REPOSITORY", "")
    ref = env.get("GITHUB_REF", "")
    if ref != f"refs/tags/{tag}":
        raise SourceMismatch(f"GITHUB_REF {ref!r} is not refs/tags/{tag}")
    workflow_ref = env.get("GITHUB_WORKFLOW_REF", "")
    if workflow_ref != f"{repo}/{WORKFLOW_PATH}@refs/tags/{tag}":
        raise SourceMismatch(f"workflow {workflow_ref!r} is not {repo}/{WORKFLOW_PATH}@refs/tags/{tag}")
    sha = env.get("GITHUB_SHA", "")
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise SourceMismatch(f"GITHUB_SHA {sha!r} is not a commit")
    return {"repository": f"{server}/{repo}", "tag": tag, "ref": ref, "commit": sha,
            "workflow": WORKFLOW_PATH, "server": server, "repo": repo}


def provenance(env: Mapping[str, str], *, tag: str, artifact: str, build: Mapping[str, str]) -> dict:
    src = _source(env, tag)
    run = f"{src['repository']}/actions/runs/{env.get('GITHUB_RUN_ID', '')}/attempts/{env.get('GITHUB_RUN_ATTEMPT', '1')}"
    return {
        "buildDefinition": {
            "buildType": BUILD_TYPE,
            "externalParameters": {
                "workflow": {"repository": src["repository"], "path": WORKFLOW_PATH, "ref": src["ref"]},
                "sourceTag": tag,
                "artifact": artifact,
                **{k: v for k, v in build.items() if v},
            },
            "internalParameters": {
                "github": {
                    "event_name": env.get("GITHUB_EVENT_NAME", ""),
                    "repository_id": env.get("GITHUB_REPOSITORY_ID", ""),
                    "repository_owner_id": env.get("GITHUB_REPOSITORY_OWNER_ID", ""),
                    "runner_environment": env.get("RUNNER_ENVIRONMENT", ""),
                }
            },
            "resolvedDependencies": [
                {"uri": f"git+{src['repository']}@{src['ref']}", "digest": {"gitCommit": src["commit"]}}
            ],
        },
        "runDetails": {
            "builder": {"id": f"{src['repository']}/{WORKFLOW_PATH}@{src['ref']}"},
            "metadata": {"invocationId": run,
                         "startedOn": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")},
        },
    }


def _require_digest(item: Mapping, where: str) -> None:
    if not DIGEST_RE.match(str(item.get("digest", ""))):
        raise ValueError(f"{where}: {item.get('ref') or item.get('name')} has no sha256 digest")


def manifest(env: Mapping[str, str], *, tag: str, digests_dir: Path, upstream: Mapping,
             charts: list[Mapping]) -> dict:
    src = _source(env, tag)
    images = [json.loads(p.read_text()) for p in sorted(Path(digests_dir).glob("*.json"))]
    for item in images:
        _require_digest(item, "first-party image")
    for item in upstream.get("images", []):
        _require_digest(item, "upstream image")
    for item in charts:
        _require_digest(item, "chart")
    return {
        "version": tag.removeprefix("v").removesuffix("-ce"),
        "source": {k: src[k] for k in ("repository", "tag", "commit", "workflow")},
        "images": images,
        "charts": list(charts),
        "upstream": list(upstream.get("images", [])),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("provenance")
    p.add_argument("--tag", required=True)
    p.add_argument("--artifact", required=True)
    p.add_argument("--dockerfile", default="")
    p.add_argument("--out", required=True)
    m = sub.add_parser("manifest")
    m.add_argument("--tag", required=True)
    m.add_argument("--digests", required=True)
    m.add_argument("--upstream", required=True)
    m.add_argument("--charts", required=True)
    m.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    try:
        if args.cmd == "provenance":
            doc = provenance(os.environ, tag=args.tag, artifact=args.artifact,
                             build={"dockerfile": args.dockerfile})
        else:
            doc = manifest(os.environ, tag=args.tag, digests_dir=Path(args.digests),
                           upstream=json.loads(Path(args.upstream).read_text()),
                           charts=json.loads(Path(args.charts).read_text()))
    except (SourceMismatch, ValueError) as exc:
        print(f"release_attest: {exc}", file=sys.stderr)
        return 1
    Path(args.out).write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
