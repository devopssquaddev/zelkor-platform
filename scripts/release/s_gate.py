#!/usr/bin/env python3
"""CE S-gate runner: run every required S-id from s_gate.yaml and judge each one.

`plan` prints what would run and which S-ids are already GAP (missing test file or env).
`run` runs pytest on the files of the chosen profile (window sweep last), writes the JUnit with the
release properties (tests/conftest.py) and prints a per-S-id verdict. An S-id is PASS only when it
has a passing case and none skipped (cases named test_sNN_* for that id; else every case of its
files). Exit 1 when any S-id is not PASS: an absent or skipped required S-id blocks the tag.

Usage: s_gate.py plan|run [--profile full|perimeter] [--junit FILE] [-- extra pytest args]
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MANIFEST = HERE / "s_gate.yaml"
sys.path.insert(0, str(HERE))
import fail_closed_matrix as fcm  # noqa: E402


@dataclass
class Item:
    s_id: str
    files: list[str]
    env: list[str]
    profile: str = "full"
    missing_files: list[str] = field(default_factory=list)
    missing_env: list[str] = field(default_factory=list)

    @property
    def stems(self) -> set[str]:
        return {Path(f).stem for f in self.files}


def load(path: Path = MANIFEST) -> dict:
    return yaml.safe_load(path.read_text())


def items(manifest: dict, profile: str, env: dict[str, str], root: Path = ROOT) -> list[Item]:
    out = []
    for sid, spec in manifest["s_ids"].items():
        it = Item(sid, list(spec["files"]), list(spec.get("env") or []), spec.get("profile", "full"))
        if it.profile != profile:
            continue
        it.missing_files = [f for f in it.files if not (root / f).is_file()]
        it.missing_env = [e for e in it.env if not env.get(e)]
        out.append(it)
    return out


def verdicts(its: list[Item], cases: list[fcm.Case]) -> dict[str, tuple[str, Counter]]:
    out = {}
    for it in its:
        mine = [c for c in cases if c.module in it.stems]
        named = [c for c in mine if it.s_id in fcm.s_ids(c.classname, c.name)]
        counts = Counter(c.outcome for c in (named or mine))
        if it.missing_files or it.missing_env:
            status = "GAP"
        elif counts["failed"]:
            status = "FAIL"
        elif counts["passed"] and not counts["skipped"]:
            status = "PASS"
        else:
            status = "GAP"
        out[it.s_id] = (status, counts)
    return out


def _plan_lines(its: list[Item], missing_global: list[str]) -> list[str]:
    lines = []
    if missing_global:
        lines.append(f"GAP all: global env unset: {', '.join(missing_global)}")
    for it in its:
        why = [f"no file {f}" for f in it.missing_files] + [f"env {e} unset" for e in it.missing_env]
        if why:
            lines.append(f"GAP {it.s_id}: {'; '.join(why)}")
    return lines


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    extra = argv[argv.index("--") + 1:] if "--" in argv else []
    argv = argv[: argv.index("--")] if "--" in argv else argv
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=["plan", "run"])
    ap.add_argument("--profile", default="full", choices=["full", "perimeter"])
    ap.add_argument("--junit", default="s-gate.junit.xml")
    args = ap.parse_args(argv)

    manifest = load()
    env = dict(os.environ)
    its = items(manifest, args.profile, env)
    missing_global = [e for e in manifest["global_env"] if not env.get(e)]
    for line in _plan_lines(its, missing_global):
        print(line)
    last = [f for f in manifest.get("last") or [] if (ROOT / f).is_file()]
    files = sorted({f for it in its for f in it.files if f not in it.missing_files} - set(last)) + last
    if args.cmd == "plan":
        print(f"{args.profile}: {len(its)} S-ids, {len(files)} files")
        for f in files:
            print(f"  {f}")
        return 1 if missing_global or any(it.missing_files or it.missing_env for it in its) else 0
    if missing_global:
        print("refusing to run: the evidence would not be bound to a release (see global_env)", file=sys.stderr)
        return 1
    # pytest runs files in argument order, so the window sweep stays last.
    rc = subprocess.run([sys.executable, "-m", "pytest", *files, "-o", "addopts=", "-rs",
                         f"--junitxml={args.junit}", *extra], cwd=ROOT).returncode
    junit = Path(args.junit) if Path(args.junit).is_absolute() else ROOT / args.junit
    if not junit.is_file():
        print(f"pytest wrote no JUnit (exit {rc})", file=sys.stderr)
        return 1
    result = verdicts(its, fcm.parse_junit(junit))
    print("\n| S-id | Verdict | Passed | Failed | Skipped |\n| :--- | :--- | ---: | ---: | ---: |")
    for sid, (status, c) in result.items():
        print(f"| {sid} | {status} | {c['passed']} | {c['failed']} | {c['skipped']} |")
    bad = [sid for sid, (status, _) in result.items() if status != "PASS"]
    if bad:
        print(f"\nS-gate {args.profile}: NOT PASS for {', '.join(bad)}", file=sys.stderr)
    return 1 if bad or rc != 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
