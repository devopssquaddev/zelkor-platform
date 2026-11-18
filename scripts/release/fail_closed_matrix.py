#!/usr/bin/env python3
"""CE-19e: publish the fail-closed negative matrix of a release from its S-gate JUnit XML.

Groups S-gate test outcomes into the categories of fail_closed_categories.yaml. Status per category:
FAIL if any test failed or errored; PASS only when every oracle S-id of the category has a passing
case and none of its cases skipped; GAP otherwise (SKIP is never PASS, a non-oracle pass never earns
PASS). Only test names and counts are published, never failure text.
Missing evidence writes an all-GAP matrix with a banner and a workflow warning.

Evidence is bound to the release by JUnit testsuite properties (written by tests/conftest.py from
ZELKOR_SGATE_VERSION / ZELKOR_SGATE_GIT_SHA / ZELKOR_SGATE_RUN_ID). --require-evidence checks them: the tested release
must equal the tag, or the tested commit must differ from the tag in no product path (carry-over).

Usage: fail_closed_matrix.py --tag vX.Y.Z-ce --junit FILE --out FILE [--mapping FILE]
                             [--require-evidence [--repo DIR]] [--strict]
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
DEFAULT_MAPPING = HERE / "fail_closed_categories.yaml"
S_GATE = HERE / "s_gate.yaml"
SID_RE = re.compile(r"S-\d{2}")
NAME_SID_RE = re.compile(r"(?:^|[._])test_s(\d{2})(?=_|$)", re.I)
OUTCOMES = ("passed", "failed", "skipped")
TAG_RE = re.compile(r"^v(\d+\.\d+\.\d+)-ce$")
# Paths whose change invalidates S-gate evidence from an earlier commit (what customers run).
PRODUCT_PATHS = ("charts", "images", "agents", "mcp", "cli", "profiles", "scripts/install-engine.sh",
                 "scripts/lib", "install.sh")
EVIDENCE_PROPS = ("zelkor_release", "zelkor_git_sha", "zelkor_run_id")


@dataclass(frozen=True)
class Case:
    classname: str
    name: str
    outcome: str  # passed | failed | skipped (error counts as failed)

    @property
    def module(self) -> str:
        """File stem of the test; a trailing class segment (tests.test_x.TestY) is dropped."""
        parts = [p for p in self.classname.split(".") if p]
        for part in reversed(parts):
            if part.startswith("test_"):
                return part
        return parts[-1] if parts else ""


@dataclass
class Row:
    key: str
    title: str
    oracles: frozenset = frozenset()
    counts: Counter = field(default_factory=Counter)
    seen: set = field(default_factory=set)
    oracle_passed: set = field(default_factory=set)
    oracle_skipped: set = field(default_factory=set)

    @property
    def missing(self) -> list[str]:
        """Oracle S-ids without a clean pass (absent, or skipped in any case)."""
        return sorted((self.oracles - self.oracle_passed) | (self.oracles & self.oracle_skipped))

    @property
    def status(self) -> str:
        if self.counts["failed"]:
            return "FAIL"
        return "PASS" if self.oracles and not self.missing else "GAP"


@dataclass
class Other:
    module: str
    s_ids: list
    counts: Counter


@dataclass
class Report:
    categories: list
    other: list
    evidence: bool = True
    properties: dict = field(default_factory=dict)


def s_ids(classname: str, name: str) -> set[str]:
    out = set()
    for part in (classname.split(".")[-1], name):
        for m in NAME_SID_RE.finditer(part):
            out.add(f"S-{m.group(1)}")
    return out


def _root(path: Path) -> ET.Element:
    try:
        return ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise ValueError(f"{path}: not JUnit XML ({exc})") from exc


def parse_properties(path: Path) -> dict[str, str]:
    return {p.get("name", ""): p.get("value", "") for p in _root(path).iter("property")}


def parse_junit(path: Path) -> list[Case]:
    root = _root(path)
    cases = []
    for tc in root.iter("testcase"):
        if tc.find("failure") is not None or tc.find("error") is not None:
            outcome = "failed"
        elif tc.find("skipped") is not None:
            outcome = "skipped"
        else:
            outcome = "passed"
        cases.append(Case(tc.get("classname", ""), tc.get("name", ""), outcome))
    return cases


def load_mapping(path: Path = DEFAULT_MAPPING) -> dict:
    return yaml.safe_load(path.read_text())["categories"]


def file_s_ids(path: Path = S_GATE) -> dict[str, set[str]]:
    """test file stem -> the S-ids s_gate.yaml proves with it (for cases whose names carry no S-id)."""
    if not path.is_file():
        return {}
    out: dict[str, set[str]] = {}
    for sid, spec in (yaml.safe_load(path.read_text()).get("s_ids") or {}).items():
        for f in spec.get("files") or []:
            out.setdefault(Path(f).stem, set()).add(sid)
    return out


def build(mapping: dict, cases: list[Case], by_file: dict[str, set[str]] | None = None) -> Report:
    rows = {k: Row(k, v["title"], frozenset(v.get("oracle_s_ids") or [])) for k, v in mapping.items()}
    other: dict[str, Other] = {}
    for case in cases:
        ids = s_ids(case.classname, case.name) or set((by_file or {}).get(case.module, set()))
        hit = False
        for key, cat in mapping.items():
            if ids & set(cat.get("s_ids") or []) or case.module in (cat.get("files") or []):
                row = rows[key]
                row.counts[case.outcome] += 1
                row.seen |= ids
                hit_oracles = ids & row.oracles
                if case.outcome == "passed":
                    row.oracle_passed |= hit_oracles
                elif case.outcome == "skipped":
                    row.oracle_skipped |= hit_oracles
                hit = True
        if not hit:
            o = other.setdefault(case.module, Other(case.module, sorted(ids), Counter()))
            o.s_ids = sorted(set(o.s_ids) | ids)
            o.counts[case.outcome] += 1
    return Report(list(rows.values()), sorted(other.values(), key=lambda o: o.module))


def evidence_problems(props: dict[str, str], tag: str, repo: Path) -> list[str]:
    """Why this JUnit is not evidence for `tag` (empty list = bound to the tag)."""
    m = TAG_RE.match(tag)
    if not m:
        return [f"tag {tag!r} is not vX.Y.Z-ce"]
    missing = [p for p in EVIDENCE_PROPS if not props.get(p)]
    if missing:
        return [f"JUnit lacks testsuite properties {', '.join(missing)} (run the S-gate via scripts/release/run_s_gate.sh)"]
    if props["zelkor_release"] == m.group(1):
        return []
    sha = props["zelkor_git_sha"]
    r = subprocess.run(["git", "-C", str(repo), "diff", "--quiet", sha, tag, "--", *PRODUCT_PATHS],
                       capture_output=True, text=True)
    if r.returncode == 0:
        return []
    if r.returncode == 1:
        return [f"evidence is for {props['zelkor_release']} at {sha[:12]}; product paths changed before {tag}"]
    return [f"cannot compare {sha[:12]} with {tag}: {r.stderr.strip() or 'git diff failed'}"]


def render(report: Report, *, tag: str, source: str = "") -> str:
    lines = [f"# Fail-closed matrix: {tag}", ""]
    if not report.evidence:
        lines += ["> **No S-gate evidence attached for this release.** Every category is GAP until the "
                  "S-gate JUnit is published.", ""]
    else:
        run = report.properties
        tested = (f" Tested release `{run['zelkor_release']}`, commit `{run.get('zelkor_git_sha', '')[:12]}`, "
                  f"run `{run.get('zelkor_run_id', '')}`." if run.get("zelkor_release") else "")
        lines += [f"Generated from the S-gate run{f' (`{source}`)' if source else ''}.{tested} "
                  "A category is PASS only when every oracle S-id passed and none skipped; "
                  "SKIP never counts as PASS.", ""]
    lines += ["| Category | Status | Passed | Failed | Skipped | S-ids run | Oracles missing |",
              "| :--- | :--- | ---: | ---: | ---: | :--- | :--- |"]
    for r in report.categories:
        missing = ", ".join(r.missing) if r.oracles else "no oracle mapped"
        lines.append(f"| {r.title} | {r.status} | {r.counts['passed']} | {r.counts['failed']} | "
                     f"{r.counts['skipped']} | {', '.join(sorted(r.seen)) or '-'} | {missing or '-'} |")
    if report.other:
        lines += ["", "## Not mapped to a category", "",
                  "| Test module | S-ids | Passed | Failed | Skipped |", "| :--- | :--- | ---: | ---: | ---: |"]
        for o in report.other:
            lines.append(f"| `{o.module}` | {', '.join(o.s_ids) or '-'} | {o.counts['passed']} | "
                         f"{o.counts['failed']} | {o.counts['skipped']} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tag", required=True)
    ap.add_argument("--junit", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--mapping", default=str(DEFAULT_MAPPING))
    ap.add_argument("--require-evidence", action="store_true",
                    help="exit 1 when the JUnit is missing, not bound to the tag, or a category FAILs")
    ap.add_argument("--repo", default=".", help="git checkout holding the tag (carry-over check)")
    ap.add_argument("--strict", action="store_true", help="also exit 1 on any GAP")
    args = ap.parse_args(argv)
    mapping = load_mapping(Path(args.mapping))
    junit = Path(args.junit)
    if junit.is_file():
        report = build(mapping, parse_junit(junit), file_s_ids())
        report.properties = parse_properties(junit)
    else:
        report = Report([Row(k, v["title"], frozenset(v.get("oracle_s_ids") or [])) for k, v in mapping.items()],
                        [], evidence=False)
        print(f"::warning title=fail-closed matrix::no S-gate evidence at {args.junit}; every category is GAP")
    Path(args.out).write_text(render(report, tag=args.tag, source=args.junit if report.evidence else ""))
    summary = Counter(r.status for r in report.categories)
    print(f"fail-closed matrix {args.tag}: " + ", ".join(f"{k}={summary[k]}" for k in ("PASS", "FAIL", "GAP")))
    if args.require_evidence:
        if not report.evidence:
            return 1
        problems = evidence_problems(report.properties, args.tag, Path(args.repo))
        for p in problems:
            print(f"::error title=fail-closed matrix::{p}")
        if problems or summary["FAIL"]:
            return 1
    if args.strict and summary["GAP"]:
        print(f"::error title=fail-closed matrix::{summary['GAP']} categories are GAP")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
