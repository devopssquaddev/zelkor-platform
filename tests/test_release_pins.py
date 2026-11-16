"""CE-19a: workflow pin audit and the first-party image list (offline).

Every `uses:` is a 40-hex commit SHA with a `# vX` comment; tool downloads name a version.
The release matrix comes from scripts/build-images.sh, never a hand-kept YAML list.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "release"))

import pin_audit  # noqa: E402

BUILD = ROOT / "scripts" / "build-images.sh"
SHA = "11d5960a326750d5838078e36cf38b85af677262"


def _audit(tmp_path: Path, text: str) -> list[str]:
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "x.yml").write_text(text)
    return [f.message for f in pin_audit.audit_repo(tmp_path)]


def test_repo_workflows_pass_pin_audit():
    findings = pin_audit.audit_repo(ROOT)
    assert not findings, "\n".join(str(f) for f in findings)


def test_pin_audit_covers_composite_actions(tmp_path):
    action = tmp_path / ".github" / "actions" / "x" / "action.yml"
    action.parent.mkdir(parents=True)
    action.write_text("runs:\n  using: composite\n  steps:\n    - uses: actions/checkout@v4\n")
    assert [f.path.name for f in pin_audit.audit_repo(tmp_path)] == ["action.yml"]


@pytest.mark.parametrize(
    "line, needle",
    [
        ("      - uses: actions/checkout@v4", "40-hex"),
        ("      - uses: actions/checkout@main", "40-hex"),
        ("      - uses: actions/checkout", "no version"),
        (f"      - uses: actions/checkout@{SHA}", "# vX"),
        ("      - uses: docker://alpine:3.20", "sha256"),
    ],
)
def test_unpinned_uses_fails(tmp_path, line, needle):
    msgs = _audit(tmp_path, f"jobs:\n  a:\n    steps:\n{line}\n")
    assert msgs and needle in msgs[0], msgs


def test_pinned_and_local_uses_pass(tmp_path):
    text = (
        "jobs:\n  a:\n    steps:\n"
        f"      - uses: actions/checkout@{SHA} # v4.4.0\n"
        "      - uses: ./.github/actions/release-image\n"
        "      - uses: docker://alpine@sha256:" + "a" * 64 + "\n"
    )
    assert _audit(tmp_path, text) == []


@pytest.mark.parametrize(
    "run, needle",
    [
        ("python -m pip install --upgrade pip pip-audit", "pip"),
        ("pip install pip-audit>=2", "pip-audit>=2"),
        ("npm install -g wrangler", "wrangler"),
        ("go install sigs.k8s.io/kind@latest", "@latest"),
        ("curl -sL https://github.com/x/y/releases/latest/download/y -o y", "latest"),
        ("curl -sSL https://example.com/install.sh | bash", "pipe"),
    ],
)
def test_unpinned_tool_download_fails(tmp_path, run, needle):
    msgs = _audit(tmp_path, f"jobs:\n  a:\n    steps:\n      - run: |\n          {run}\n")
    assert msgs and needle in msgs[0], msgs


def test_pinned_tool_downloads_pass(tmp_path):
    text = (
        "jobs:\n  a:\n    steps:\n      - run: |\n"
        "          python -m pip install pip-audit==2.10.1\n"
        "          pip install -r requirements-dev.txt\n"
        "          python -m pip install \\\n            pyyaml==6.0.2\n"
        "          npm ci\n"
        "          go install sigs.k8s.io/kind@v0.33.0\n"
        "          curl -sSLo kind https://github.com/kubernetes-sigs/kind/releases/download/v0.33.0/kind-linux-amd64\n"
    )
    assert _audit(tmp_path, text) == []


def test_with_version_latest_fails(tmp_path):
    text = (
        "jobs:\n  a:\n    steps:\n"
        f"      - uses: sigstore/cosign-installer@{SHA} # v4.1.3\n"
        "        with:\n          cosign-release: latest\n"
    )
    msgs = _audit(tmp_path, text)
    assert msgs and "latest" in msgs[0]


def test_cli_exit_code(tmp_path):
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "x.yml").write_text("jobs:\n  a:\n    steps:\n      - uses: actions/checkout@v4\n")
    r = subprocess.run([sys.executable, str(ROOT / "scripts/release/pin_audit.py"), str(tmp_path)],
                       capture_output=True, text=True)
    assert r.returncode == 1
    assert "x.yml:4" in r.stdout


# --- scripts/build-images.sh: single source of the first-party image list ---


def _build(*args: str, **env: str) -> subprocess.CompletedProcess[str]:
    full = {k: v for k, v in os.environ.items() if k not in ("GITHUB_ACTIONS", "IMAGE_TAG", "IMAGES")}
    full.update(env)
    return subprocess.run(["bash", str(BUILD), *args], capture_output=True, text=True, env=full, cwd=ROOT)


def test_list_matches_list_json_and_dockerfiles_exist():
    names = _build("--list").stdout.split()
    plan = json.loads(_build("--list-json").stdout)
    assert names and [p["name"] for p in plan] == names
    for p in plan:
        assert (ROOT / p["dockerfile"]).is_file(), p
        assert p["name"].startswith("zelkor-")


def test_list_json_tiers_follow_first_party_bases():
    plan = {p["name"]: p for p in json.loads(_build("--list-json").stdout)}
    assert plan["zelkor-aegra"]["tier"] == 0 and plan["zelkor-aegra"]["base"] == ""
    assert plan["zelkor-aegra-deep"]["base"] == "zelkor-aegra"
    assert plan["zelkor-aegra-deep"]["tier"] == 1
    assert plan["zelkor-example-finserve-coder"]["tier"] == 2
    for p in plan.values():
        if p["base"]:
            assert plan[p["base"]]["tier"] == p["tier"] - 1


def test_examples_images_are_in_the_release_list():
    names = set(_build("--list").stdout.split())
    assert {"zelkor-example-finserve", "zelkor-example-finserve-coder", "zelkor-armored-gpt-researcher"} <= names


def test_security_scan_matrix_is_subset_of_release_list():
    import yaml

    wf = yaml.safe_load((ROOT / ".github/workflows/security-scan.yml").read_text())
    scanned = set(wf["jobs"]["trivy-images"]["strategy"]["matrix"]["image"])
    assert scanned <= set(_build("--list").stdout.split())


@pytest.mark.parametrize("tag", ["2.4.6", "10.0.1"])
def test_semver_push_refused_outside_ci(tag):
    r = _build("--push", IMAGE_TAG=tag, IMAGES="zelkor-aegra")
    assert r.returncode != 0
    assert "release tags are pushed by CI only" in r.stderr


def test_semver_push_guard_runs_before_any_build():
    r = _build("--push", IMAGE_TAG="2.4.6", IMAGES="zelkor-aegra", PATH="/usr/bin:/bin")
    assert "docker build" not in r.stdout
