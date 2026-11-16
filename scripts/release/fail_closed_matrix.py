#!/usr/bin/env python3
"""CE-19e: publish the fail-closed negative matrix of a release from its S-gate JUnit XML.

Groups S-gate test outcomes into the categories of fail_closed_categories.yaml. Status per category:
FAIL if any test failed or errored; GAP if none passed (zero tests, or only skips: SKIP is never
PASS); PASS otherwise. Only test names and counts are published, never failure text.
Missing evidence writes an all-GAP matrix with a banner and a workflow warning.

Usage: fail_closed_matrix.py --tag vX.Y.Z-ce --junit FILE --out FILE [--mapping FILE] [--require-evidence]
"""
from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
DEFAULT_MAPPING = HERE / "fail_closed_categories.yaml"
SID_RE = re.compile(r"S-\d{2}")
NAME_SID_RE = re.compile(r"(?:^|[._])test_s(\d{2})(?=_|$)", re.I)
OUTCOMES = ("passed", "failed", "skipped")


@dataclass(frozen=True)
class Case:
    classname: str
    name: str
    outcome: str  # passed | failed | skipped (error counts as failed)

    @property
    def module(self) -> str:
        return self.classname.split(".")[-1] if self.classname else ""


@dataclass
class Row:
    key: str
    title: str
    counts: Counter = field(default_factory=Counter)
    seen: set = field(default_factory=set)

    @property
    def status(self) -> str:
        if self.counts["failed"]:
            return "FAIL"
        return "PASS" if self.counts["passed"] else "GAP"


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


def s_ids(classname: str, name: str) -> set[str]:
    out = set()
    for part in (classname.split(".")[-1], name):
        for m in NAME_SID_RE.finditer(part):
            out.add(f"S-{m.group(1)}")
    return out


def parse_junit(path: Path) -> list[Case]:
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise ValueError(f"{path}: not JUnit XML ({exc})") from exc
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


def build(mapping: dict, cases: list[Case]) -> Report:
    rows = {k: Row(k, v["title"]) for k, v in mapping.items()}
    other: dict[str, Other] = {}
    for case in cases:
        ids = s_ids(case.classname, case.name)
        hit = False
        for key, cat in mapping.items():
            if ids & set(cat.get("s_ids") or []) or case.module in (cat.get("files") or []):
                rows[key].counts[case.outcome] += 1
                rows[key].seen |= ids
                hit = True
        if not hit:
            o = other.setdefault(case.module, Other(case.module, sorted(ids), Counter()))
            o.s_ids = sorted(set(o.s_ids) | ids)
            o.counts[case.outcome] += 1
    return Report(list(rows.values()), sorted(other.values(), key=lambda o: o.module))


def render(report: Report, *, tag: str, source: str = "") -> str:
    lines = [f"# Fail-closed matrix: {tag}", ""]
    if not report.evidence:
        lines += ["> **No S-gate evidence attached for this release.** Every category is GAP until the "
                  "S-gate JUnit is published.", ""]
    else:
        lines += [f"Generated from the S-gate run{f' (`{source}`)' if source else ''}. "
                  "SKIP never counts as PASS; a category with no passing test is a GAP.", ""]
    lines += ["| Category | Status | Passed | Failed | Skipped | S-ids run |",
              "| :--- | :--- | ---: | ---: | ---: | :--- |"]
    for r in report.categories:
        lines.append(f"| {r.title} | {r.status} | {r.counts['passed']} | {r.counts['failed']} | "
                     f"{r.counts['skipped']} | {', '.join(sorted(r.seen)) or '-'} |")
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
    ap.add_argument("--require-evidence", action="store_true", help="exit 1 when the JUnit file is missing")
    args = ap.parse_args(argv)
    mapping = load_mapping(Path(args.mapping))
    junit = Path(args.junit)
    if junit.is_file():
        report = build(mapping, parse_junit(junit))
    else:
        report = Report([Row(k, v["title"]) for k, v in mapping.items()], [], evidence=False)
        print(f"::warning title=fail-closed matrix::no S-gate evidence at {args.junit}; every category is GAP")
    Path(args.out).write_text(render(report, tag=args.tag, source=args.junit if report.evidence else ""))
    summary = Counter(r.status for r in report.categories)
    print(f"fail-closed matrix {args.tag}: " + ", ".join(f"{k}={summary[k]}" for k in ("PASS", "FAIL", "GAP")))
    if args.require_evidence and not report.evidence:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
