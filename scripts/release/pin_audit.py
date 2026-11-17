#!/usr/bin/env python3
"""CE-19a pin audit: every GitHub Action and tool download in CI names an immutable version.

Fails when, in .github/workflows/*.yml or .github/actions/**/action.yml:
  - a `uses:` is not `owner/repo[/path]@<40-hex SHA>` followed by a `# vX` comment
    (local `./` actions are fine; `docker://` needs `@sha256:`),
  - a `with:` version input is `latest`,
  - a run step installs a tool without a version: `pip install pkg` without `==`,
    `npm install -g pkg` without `@<version>`, `go install …@latest`, a download URL
    through `/latest/`, or a remote script piped into a shell.

Usage: pin_audit.py [repo_root]   (exit 1 and one `file:line: message` per finding)
"""
from __future__ import annotations

import re
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
USES_RE = re.compile(r"^\s*(?:-\s+)?uses:\s*['\"]?(?P<ref>[^\s'\"#]+)['\"]?\s*(?:#\s*(?P<comment>.*))?$")
VERSION_COMMENT_RE = re.compile(r"^v?\d+(\.\d+)*\S*")
WITH_VERSION_RE = re.compile(r"^\s*[\w-]*(version|release)[\w-]*:\s*['\"]?latest['\"]?\s*(#.*)?$", re.I)
PIP_RE = re.compile(r"\bpip3?\s+install\b(?P<rest>.*)")
NPM_RE = re.compile(r"\bnpm\s+(?:install|i)\s+(?P<rest>.*)")
GO_RE = re.compile(r"\bgo\s+install\s+(?P<rest>.*)")
URL_RE = re.compile(r"https?://\S+")
PIPE_SHELL_RE = re.compile(r"\b(curl|wget)\b[^|]*\|\s*(sudo\s+)?(ba|z)?sh\b")

# pip flags that take a value (the value is not a package)
PIP_VALUE_FLAGS = {"-r", "--requirement", "-c", "--constraint", "-i", "--index-url",
                   "--extra-index-url", "-t", "--target", "--prefix", "-f", "--find-links"}


@dataclass(frozen=True)
class Finding:
    path: Path
    line: int
    message: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.message}"


def workflow_files(root: Path) -> list[Path]:
    gh = root / ".github"
    files = sorted(gh.glob("workflows/*.yml")) + sorted(gh.glob("workflows/*.yaml"))
    files += sorted(gh.glob("actions/**/action.yml")) + sorted(gh.glob("actions/**/action.yaml"))
    return files


def check_uses(ref: str, comment: str | None) -> str | None:
    if ref.startswith("./"):
        return None
    if ref.startswith("docker://"):
        if not re.search(r"@sha256:[0-9a-f]{64}$", ref):
            return f"{ref}: docker action must be pinned by @sha256 digest"
        return None
    if "@" not in ref:
        return f"{ref}: no version; pin to a 40-hex commit SHA"
    _, ver = ref.rsplit("@", 1)
    if not SHA_RE.match(ver):
        return f"{ref}: not pinned to a 40-hex commit SHA"
    if not comment or not VERSION_COMMENT_RE.match(comment.strip()):
        return f"{ref}: add a `# vX.Y.Z` comment naming the tag the SHA resolves"
    return None


def _pip_packages(rest: str) -> list[str]:
    try:
        tokens = shlex.split(rest.split("#", 1)[0].split("&&", 1)[0].split(";", 1)[0])
    except ValueError:
        tokens = rest.split()
    out, skip = [], False
    for tok in tokens:
        if skip:
            skip = False
            continue
        if tok in PIP_VALUE_FLAGS:
            skip = True
            continue
        if tok.startswith("-") or tok in (".", "..") or tok.startswith(("./", "/", "$")):
            continue
        out.append(tok)
    return out


def check_run_line(text: str) -> str | None:
    m = PIP_RE.search(text)
    if m:
        for pkg in _pip_packages(m.group("rest")):
            if "==" not in pkg and not pkg.endswith((".whl", ".tar.gz")):
                return f"pip install {pkg}: pin an exact version (pkg==X.Y.Z)"
    m = NPM_RE.search(text)
    if m and re.search(r"(^|\s)(-g|--global)(\s|$)", m.group("rest")):
        for tok in m.group("rest").split():
            if tok.startswith("-"):
                continue
            if not re.search(r".@\d", tok):
                return f"npm install -g {tok}: pin a version (pkg@X.Y.Z)"
    m = GO_RE.search(text)
    if m:
        for tok in m.group("rest").split():
            if tok.startswith("-"):
                continue
            if "@" not in tok or tok.endswith(("@latest", "@main", "@master")):
                return f"go install {tok}: pin a version (@vX.Y.Z), not @latest"
    if PIPE_SHELL_RE.search(text):
        return "remote script piped into a shell: download a versioned artifact and verify it"
    for url in URL_RE.findall(text):
        if re.search(r"/latest(/|$)|[/=]latest\b", url):
            return f"{url}: download a versioned release, not latest"
    return None


def _logical_lines(lines: list[str]):
    """Yield (lineno, text) with shell `\\` continuations joined."""
    buf, start = "", 0
    for i, line in enumerate(lines, 1):
        if not buf:
            start = i
        if line.rstrip().endswith("\\"):
            buf += line.rstrip()[:-1] + " "
            continue
        yield start, buf + line
        buf = ""
    if buf:
        yield start, buf


def audit_file(path: Path, root: Path | None = None) -> list[Finding]:
    rel = path.relative_to(root) if root else path
    findings: list[Finding] = []
    for lineno, text in _logical_lines(path.read_text().splitlines()):
        if text.lstrip().startswith("#"):
            continue
        m = USES_RE.match(text)
        if m:
            msg = check_uses(m.group("ref"), m.group("comment"))
        elif WITH_VERSION_RE.match(text):
            msg = f"{text.strip()}: pin an exact version, not latest"
        else:
            msg = check_run_line(text)
        if msg:
            findings.append(Finding(rel, lineno, msg))
    return findings


def audit_repo(root: Path) -> list[Finding]:
    out: list[Finding] = []
    for f in workflow_files(root):
        out += audit_file(f, root)
    return out


def main(argv: list[str]) -> int:
    root = Path(argv[1] if len(argv) > 1 else ".").resolve()
    findings = audit_repo(root)
    for f in findings:
        print(f)
    if findings:
        print(f"pin-audit: {len(findings)} unpinned reference(s)", file=sys.stderr)
        return 1
    print(f"pin-audit: {len(workflow_files(root))} file(s) clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
