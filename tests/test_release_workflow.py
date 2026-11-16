"""CE-19b/c: release workflow contract, source-tag check, provenance, upstream digests (offline)."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "release"))

import check_version  # noqa: E402
import release_attest  # noqa: E402
import upstream_digests  # noqa: E402

sys.path.insert(0, str(ROOT / "cli" / "src"))
from zelkor import verify_cmd  # noqa: E402

RELEASE = ROOT / ".github" / "workflows" / "release.yml"
ACTION = ROOT / ".github" / "actions" / "release-image" / "action.yml"
CHART_VERSION = yaml.safe_load((ROOT / "charts/zelkor-platform/Chart.yaml").read_text())["version"]
TAG = f"v{CHART_VERSION}-ce"


def _wf() -> dict:
    data = yaml.safe_load(RELEASE.read_text())
    data["on"] = data.pop(True, data.get("on"))  # YAML 1.1 reads `on:` as True
    return data


# --- source tag == Chart.yaml == image tags -----------------------------------------------


def test_current_tree_matches_its_ce_tag():
    version, errors = check_version.check(ROOT, TAG)
    assert errors == [] and version == CHART_VERSION


@pytest.mark.parametrize("tag", ["v9.9.9-ce", f"v{CHART_VERSION}", CHART_VERSION, f"v{CHART_VERSION}-ce-rc1"])
def test_wrong_or_malformed_tag_fails(tag):
    _, errors = check_version.check(ROOT, tag)
    assert errors


def _copy_tree(tmp_path: Path) -> Path:
    dst = tmp_path / "repo"
    for rel in ("charts", "examples", "images", "scripts/build-images.sh"):
        src = ROOT / rel
        if src.is_dir():
            shutil.copytree(src, dst / rel, ignore=shutil.ignore_patterns("node_modules", "*.tgz", "tests"))
        else:
            (dst / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst / rel)
    return dst


def test_values_image_tag_mismatch_fails(tmp_path):
    repo = _copy_tree(tmp_path)
    values = repo / "charts/zelkor-platform/values.yaml"
    text = values.read_text()
    needle = f"repository: ghcr.io/devopssquaddev/zelkor-mcp\n      tag: {CHART_VERSION}"
    assert needle in text
    values.write_text(text.replace(needle, "repository: ghcr.io/devopssquaddev/zelkor-mcp\n      tag: 0.0.1"))
    _, errors = check_version.check(repo, TAG)
    assert any("zelkor-mcp" in e and "0.0.1" in e for e in errors), errors


def test_dockerfile_base_mismatch_fails(tmp_path):
    repo = _copy_tree(tmp_path)
    df = repo / "images/aegra-deep/Dockerfile"
    df.write_text(df.read_text().replace(f"zelkor-aegra:{CHART_VERSION}", "zelkor-aegra:dev"))
    _, errors = check_version.check(repo, TAG)
    assert any("aegra-deep/Dockerfile" in e for e in errors), errors


def test_chart_app_version_mismatch_fails(tmp_path):
    repo = _copy_tree(tmp_path)
    chart = repo / "charts/zelkor-agent/Chart.yaml"
    chart.write_text(chart.read_text().replace(f'appVersion: "{CHART_VERSION}"', 'appVersion: "0.0.1"'))
    _, errors = check_version.check(repo, TAG)
    assert any("zelkor-agent/Chart.yaml" in e for e in errors), errors


def test_check_version_cli_writes_github_output(tmp_path):
    out = tmp_path / "out"
    r = subprocess.run([sys.executable, str(ROOT / "scripts/release/check_version.py"), TAG,
                        "--root", str(ROOT), "--github-output", str(out)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert f"version={CHART_VERSION}" in out.read_text()
    bad = subprocess.run([sys.executable, str(ROOT / "scripts/release/check_version.py"), "v0.0.1-ce",
                          "--root", str(ROOT)], capture_output=True, text=True)
    assert bad.returncode == 1


# --- SLSA provenance predicate -------------------------------------------------------------

GH_ENV = {
    "GITHUB_REPOSITORY": "devopssquaddev/zelkor-platform",
    "GITHUB_SERVER_URL": "https://github.com",
    "GITHUB_REF": f"refs/tags/{TAG}",
    "GITHUB_REF_NAME": TAG,
    "GITHUB_SHA": "a" * 40,
    "GITHUB_WORKFLOW_REF": f"devopssquaddev/zelkor-platform/.github/workflows/release.yml@refs/tags/{TAG}",
    "GITHUB_RUN_ID": "42",
    "GITHUB_RUN_ATTEMPT": "1",
    "GITHUB_EVENT_NAME": "push",
    "RUNNER_ENVIRONMENT": "github-hosted",
}


def test_provenance_names_repo_tag_and_workflow():
    p = release_attest.provenance(GH_ENV, tag=TAG, artifact="ghcr.io/devopssquaddev/zelkor-mcp",
                                  build={"dockerfile": "images/mcp/Dockerfile"})
    wf = p["buildDefinition"]["externalParameters"]["workflow"]
    assert wf == {"repository": "https://github.com/devopssquaddev/zelkor-platform",
                  "path": ".github/workflows/release.yml", "ref": f"refs/tags/{TAG}"}
    assert p["buildDefinition"]["externalParameters"]["sourceTag"] == TAG
    dep = p["buildDefinition"]["resolvedDependencies"][0]
    assert dep["digest"] == {"gitCommit": "a" * 40}
    assert p["runDetails"]["builder"]["id"].endswith(f"/.github/workflows/release.yml@refs/tags/{TAG}")
    assert p["runDetails"]["metadata"]["invocationId"].endswith("/actions/runs/42/attempts/1")


@pytest.mark.parametrize(
    "override",
    [
        {"GITHUB_REF": "refs/heads/main"},
        {"GITHUB_REF": "refs/tags/v0.0.1-ce", "GITHUB_REF_NAME": "v0.0.1-ce"},
        {"GITHUB_WORKFLOW_REF": f"devopssquaddev/zelkor-platform/.github/workflows/other.yml@refs/tags/{TAG}"},
    ],
)
def test_provenance_refuses_a_mismatched_source(override):
    with pytest.raises(release_attest.SourceMismatch):
        release_attest.provenance({**GH_ENV, **override}, tag=TAG, artifact="x", build={})


def test_release_manifest_lists_first_party_and_upstream(tmp_path):
    d = tmp_path / "digests"
    d.mkdir()
    (d / "zelkor-mcp.json").write_text(json.dumps(
        {"name": "zelkor-mcp", "ref": "ghcr.io/devopssquaddev/zelkor-mcp:1.2.3", "digest": "sha256:" + "1" * 64}))
    upstream = {"images": [{"ref": "docker.io/langfuse/langfuse:4.76.0", "digest": "sha256:" + "2" * 64}]}
    m = release_attest.manifest(GH_ENV, tag=TAG, digests_dir=d, upstream=upstream,
                                charts=[{"name": "zelkor-platform", "ref": "oci://x", "digest": "sha256:" + "3" * 64}])
    assert m["source"]["tag"] == TAG and m["source"]["commit"] == "a" * 40
    assert m["images"][0]["digest"].endswith("1" * 64)
    assert m["upstream"][0]["ref"] == "docker.io/langfuse/langfuse:4.76.0"
    assert m["charts"][0]["name"] == "zelkor-platform"


def test_release_manifest_refuses_missing_digest(tmp_path):
    d = tmp_path / "digests"
    d.mkdir()
    (d / "zelkor-mcp.json").write_text(json.dumps({"name": "zelkor-mcp", "ref": "x", "digest": ""}))
    with pytest.raises(ValueError):
        release_attest.manifest(GH_ENV, tag=TAG, digests_dir=d, upstream={"images": []}, charts=[])


# --- CE-19c upstream images: attested digests, never mirrors ---------------------------------


def test_upstream_refs_from_values_exclude_first_party():
    refs = upstream_digests.upstream_refs(ROOT)
    names = {r.ref for r in refs}
    assert "docker.io/langfuse/langfuse:4.76.0" in names
    assert "docker.io/langfuse/langfuse-worker:4.76.0" in names
    assert "docker.io/library/busybox:1.38.0" in names
    assert "ghcr.io/cloudnative-pg/postgresql:18.6" in names
    assert not [n for n in names if "devopssquaddev/zelkor-" in n]
    assert all(r.source.startswith("charts/") for r in refs)


@pytest.mark.parametrize(
    "raw, want",
    [
        ("busybox:1.38.0", "docker.io/library/busybox:1.38.0"),
        ("langfuse/langfuse:4.76.0", "docker.io/langfuse/langfuse:4.76.0"),
        ("ghcr.io/x/y:1", "ghcr.io/x/y:1"),
        ("localhost:5000/y:1", "localhost:5000/y:1"),
    ],
)
def test_normalize_ref(raw, want):
    assert upstream_digests.normalize(raw) == want


def _rendered_images(*extra: str) -> set[str]:
    from tests.test_helm_values_schema import CHART, SECRET_SETS

    cmd = ["helm", "template", "z", str(CHART), "-n", "zelkor"]
    for s in SECRET_SETS:
        cmd += ["--set", s]
    r = subprocess.run(cmd + list(extra), capture_output=True, text=True, check=True)
    return set(re.findall(r'image(?:Name)?:\s*"?([^"\s@]+)', r.stdout))


@pytest.mark.parametrize("extra", [(), ("--set", "databases.mode=operator-cr"),
                                   ("--set", "security.sandbox.provisioning.mode=daemonset")])
def test_every_rendered_upstream_image_is_attested(extra):
    attested = {r.ref for r in upstream_digests.upstream_refs(ROOT)}
    for img in _rendered_images(*extra):
        if "devopssquaddev/zelkor-" in img:
            continue
        assert upstream_digests.normalize(img) in attested, img


def test_resolve_writes_digests_and_fails_closed(tmp_path):
    refs = upstream_digests.upstream_refs(ROOT)
    doc = upstream_digests.resolve(refs, resolver=lambda ref: "sha256:" + "f" * 64)
    assert len(doc["images"]) == len(refs)
    assert all(i["digest"] == "sha256:" + "f" * 64 for i in doc["images"])

    def broken(ref):
        raise RuntimeError("registry down")

    with pytest.raises(RuntimeError, match="registry down"):
        upstream_digests.resolve(refs, resolver=broken)
    with pytest.raises(ValueError):
        upstream_digests.resolve(refs, resolver=lambda ref: "latest")


# --- workflow + composite action contract ---------------------------------------------------


def test_release_triggers_only_on_ce_tags():
    on = _wf()["on"]
    assert set(on) == {"push"}
    assert on["push"] == {"tags": ["v*-ce"]}


def test_release_least_privilege_and_signing_jobs():
    wf = _wf()
    assert wf["permissions"] == {"contents": "read"}
    jobs = wf["jobs"]
    for name in ("images-tier0", "images-tier1", "images-tier2", "chart"):
        perms = jobs[name]["permissions"]
        assert perms["id-token"] == "write" and perms["packages"] == "write", name
        assert perms["attestations"] == "write", name
    assert jobs["images-tier1"]["needs"] == ["plan", "images-tier0"]
    assert jobs["images-tier2"]["needs"] == ["plan", "images-tier1"]


def test_plan_checks_tag_and_pins_before_building():
    steps = " ".join(s.get("run", "") for s in _wf()["jobs"]["plan"]["steps"])
    assert "scripts/release/check_version.py" in steps
    assert "scripts/release/pin_audit.py" in steps
    assert "scripts/build-images.sh --list-json" in steps


def test_image_matrix_comes_from_build_images():
    text = RELEASE.read_text()
    assert "fromJSON(needs.plan.outputs.tier0)" in text
    for name in json.loads(subprocess.run(["bash", str(ROOT / "scripts/build-images.sh"), "--list-json"],
                                          capture_output=True, text=True, check=True).stdout):
        assert name["name"] not in text, f"{name['name']} hand-listed in release.yml"


def test_image_action_signs_attests_and_sboms_by_digest():
    action = yaml.safe_load(ACTION.read_text())
    assert action["runs"]["using"] == "composite"
    text = ACTION.read_text()
    assert "scripts/build-images.sh --push" in text
    assert "cosign sign --yes" in text
    assert "--type slsaprovenance1" in text
    assert "--type spdxjson" in text
    assert "anchore/sbom-action@" in text
    assert "actions/attest-build-provenance@" in text
    assert re.search(r"@\$\{\{?\s*steps\.\w+\.outputs\.digest|@\$\{?DIGEST", text), "sign by digest"


def test_chart_job_signs_chart_and_attests_upstream_digests():
    text = json.dumps(_wf()["jobs"]["chart"])
    assert "helm push" in text and "$CHART_REPO" in text
    assert _wf()["env"]["CHART_REPO"] == "oci://ghcr.io/devopssquaddev/charts"
    assert "scripts/release/upstream_digests.py" in text
    assert "cosign sign --yes" in text
    assert release_attest.RELEASE_PREDICATE_TYPE in text
    assert "scripts/release/verify_artifacts.sh" in text


def test_no_upstream_image_is_mirrored():
    for path in (RELEASE, ACTION):
        text = path.read_text()
        assert "crane copy" not in text and "crane cp" not in text
        assert "docker tag" not in text
        assert not re.search(r"docker push\s+\S*langfuse", text)


def test_release_workflow_signs_under_the_verified_identity():
    """The cert SAN is release.yml@refs/tags/<tag>; the CLI and chart policy accept exactly that."""
    assert RELEASE.name == "release.yml" and _wf()["on"]["push"]["tags"] == ["v*-ce"]
    ident = f"https://github.com/devopssquaddev/zelkor-platform/.github/workflows/release.yml@refs/tags/{TAG}"
    assert re.match(verify_cmd.RELEASE_IDENTITY_REGEXP, ident)
    assert "workflow_call" not in RELEASE.read_text(), "a reusable workflow would change the signing identity"


def _fake_cosign(tmp_path: Path, fail_on: str = "") -> tuple[Path, Path]:
    bindir, log = tmp_path / "bin", tmp_path / "cosign.log"
    bindir.mkdir()
    (bindir / "cosign").write_text(
        "#!/usr/bin/env bash\n"
        f'echo "$*" >> "{log}"\n'
        f'if [[ -n "{fail_on}" && "$*" == *"{fail_on}"* ]]; then exit 1; fi\n'
    )
    (bindir / "cosign").chmod(0o755)
    return bindir, log


def _manifest(tmp_path: Path) -> Path:
    m = {"images": [{"name": "zelkor-mcp", "ref": "ghcr.io/devopssquaddev/zelkor-mcp:1.2.3",
                     "digest": "sha256:" + "1" * 64}],
         "charts": [{"name": "zelkor-platform", "ref": "ghcr.io/devopssquaddev/charts/zelkor-platform",
                     "digest": "sha256:" + "2" * 64}]}
    path = tmp_path / "release-manifest.json"
    path.write_text(json.dumps(m))
    return path


def _run_verify(tmp_path: Path, bindir: Path) -> subprocess.CompletedProcess[str]:
    import os

    env = {**os.environ, "PATH": f"{bindir}:{Path(sys.executable).parent}:{os.environ['PATH']}"}
    return subprocess.run(["bash", str(ROOT / "scripts/release/verify_artifacts.sh"), str(_manifest(tmp_path))],
                          capture_output=True, text=True, env=env)


def test_verify_artifacts_uses_the_chart_identity(tmp_path):
    bindir, log = _fake_cosign(tmp_path)
    r = _run_verify(tmp_path, bindir)
    assert r.returncode == 0, r.stdout + r.stderr
    calls = log.read_text().splitlines()
    iv = yaml.safe_load((ROOT / "charts/zelkor-platform/values.yaml").read_text())["security"]["imageVerification"]
    for c in calls:
        assert f"--certificate-oidc-issuer {iv['keyless']['issuer']}" in c
        assert f"--certificate-identity-regexp {iv['keyless']['subjectRegExp']}" in c
    assert any("zelkor-mcp@sha256:" + "1" * 64 in c and "--type spdxjson" in c for c in calls)
    assert any(release_attest.RELEASE_PREDICATE_TYPE in c for c in calls)
    assert len(calls) == 6


def test_verify_artifacts_fails_on_any_bad_check(tmp_path):
    bindir, _ = _fake_cosign(tmp_path, fail_on="slsaprovenance1")
    r = _run_verify(tmp_path, bindir)
    assert r.returncode == 1
    assert "FAIL" in r.stdout
