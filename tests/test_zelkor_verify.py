"""CE-19d: `zelkor verify <release>` (cosign mocked, no cluster)."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli" / "src"))

from zelkor import verify_cmd  # noqa: E402
from zelkor.main import main  # noqa: E402

DIGEST_MCP = "sha256:" + "1" * 64
DIGEST_AEGRA = "sha256:" + "2" * 64
DIGEST_LF = "sha256:" + "3" * 64


def _pod(name, containers, init=()):
    def status(c):
        image, image_id = c
        return {"name": image.split("/")[-1].split(":")[0], "image": image, "imageID": image_id}

    return {
        "metadata": {"name": name},
        "status": {"containerStatuses": [status(c) for c in containers],
                   "initContainerStatuses": [status(c) for c in init]},
    }


PODS = {
    "items": [
        _pod("zp-mcp-0", [("ghcr.io/devopssquaddev/zelkor-mcp:2.4.6",
                           f"ghcr.io/devopssquaddev/zelkor-mcp@{DIGEST_MCP}")],
             init=[("busybox:1.38.0", "docker.io/library/busybox@sha256:" + "4" * 64)]),
        _pod("zp-mcp-1", [("ghcr.io/devopssquaddev/zelkor-mcp:2.4.6",
                           f"ghcr.io/devopssquaddev/zelkor-mcp@{DIGEST_MCP}")]),
        _pod("zp-aegra-0", [("ghcr.io/devopssquaddev/zelkor-aegra:2.4.6",
                             f"ghcr.io/devopssquaddev/zelkor-aegra@{DIGEST_AEGRA}")]),
        _pod("zp-langfuse-0", [("langfuse/langfuse:4.76.0", f"docker.io/langfuse/langfuse@{DIGEST_LF}")]),
    ]
}


class Runner:
    def __init__(self, pods=PODS, cosign_fail=(), helm_rc=0, cosign_timeout=()):
        self.pods, self.cosign_fail, self.helm_rc = pods, set(cosign_fail), helm_rc
        self.cosign_timeout = set(cosign_timeout)
        self.calls: list[list[str]] = []

    def __call__(self, argv, **_kw):
        self.calls.append(list(argv))
        if argv[0] == "helm":
            return SimpleNamespace(returncode=self.helm_rc, stdout='{"name":"zp"}', stderr="release: not found")
        if argv[0] == "kubectl":
            return SimpleNamespace(returncode=0, stdout=json.dumps(self.pods), stderr="")
        if argv[0] == "cosign":
            key = (argv[1], argv[-1])
            if key in self.cosign_timeout:
                raise subprocess.TimeoutExpired(argv, 120)
            if key in self.cosign_fail:
                return SimpleNamespace(returncode=1, stdout="", stderr="Error: no matching signatures")
            return SimpleNamespace(returncode=0, stdout="[]", stderr="Verified OK")
        raise AssertionError(argv)

    def cosign_calls(self):
        return [c for c in self.calls if c[0] == "cosign"]


@pytest.fixture
def store(tmp_path):
    path = tmp_path / "envs.yaml"
    path.write_text(yaml.safe_dump({"envs": {"lab": {"kubeContext": "kind-zelkor", "namespace": "zelkor"}}}))
    return path


@pytest.fixture(autouse=True)
def cosign_on_path(monkeypatch):
    monkeypatch.setattr(verify_cmd.shutil, "which", lambda name: f"/usr/bin/{name}")


def _verify(store, runner, *extra):
    return main(["--store", str(store), "--env", "lab", "verify", "zp", *extra], runner=runner)


def test_identity_constants_match_chart_defaults():
    iv = yaml.safe_load((ROOT / "charts/zelkor-platform/values.yaml").read_text())["security"]["imageVerification"]
    assert verify_cmd.SIGSTORE_ISSUER == iv["keyless"]["issuer"]
    assert verify_cmd.RELEASE_IDENTITY_REGEXP == iv["keyless"]["subjectRegExp"]
    assert iv["images"] == [verify_cmd.IMAGE_PREFIX + "*"]


@pytest.mark.parametrize(
    "identity, ok",
    [
        ("https://github.com/devopssquaddev/zelkor-platform/.github/workflows/release.yml@refs/tags/v2.4.6-ce", True),
        ("https://github.com/devopssquaddev/zelkor-platform/.github/workflows/release.yml@refs/heads/main", False),
        ("https://github.com/devopssquaddev/zelkor-platform/.github/workflows/docs.yml@refs/tags/v2.4.6-ce", False),
        ("https://github.com/someone/zelkor-platform/.github/workflows/release.yml@refs/tags/v2.4.6-ce", False),
        ("https://github.com/devopssquaddev/zelkor-platform/.github/workflows/release.yml@refs/tags/v2.4.6-ce-x", False),
    ],
)
def test_identity_regexp_binds_release_workflow_on_ce_tags(identity, ok):
    assert bool(re.match(verify_cmd.RELEASE_IDENTITY_REGEXP, identity)) is ok


def test_all_signed_passes_and_verifies_each_digest_once(store, capsys):
    r = Runner()
    assert _verify(store, r) == 0
    calls = r.cosign_calls()
    refs = sorted({c[-1] for c in calls})
    assert refs == [f"ghcr.io/devopssquaddev/zelkor-aegra@{DIGEST_AEGRA}",
                    f"ghcr.io/devopssquaddev/zelkor-mcp@{DIGEST_MCP}"]
    assert len(calls) == 4  # verify + verify-attestation per unique digest
    for c in calls:
        assert c[c.index("--certificate-oidc-issuer") + 1] == verify_cmd.SIGSTORE_ISSUER
        assert c[c.index("--certificate-identity-regexp") + 1] == verify_cmd.RELEASE_IDENTITY_REGEXP
    att = [c for c in calls if c[1] == "verify-attestation"]
    assert all(c[c.index("--type") + 1] == "slsaprovenance1" for c in att)
    out = capsys.readouterr().out
    assert "langfuse/langfuse:4.76.0" in out and "upstream" in out


def test_selects_release_pods_by_instance_label(store):
    r = Runner()
    _verify(store, r, "--namespace", "agents")
    kube = next(c for c in r.calls if c[0] == "kubectl")
    assert "app.kubernetes.io/instance=zp" in kube
    assert kube[kube.index("-n") + 1] == "agents"
    assert "--context" in kube and "kind-zelkor" in kube


@pytest.mark.parametrize("verb", ["verify", "verify-attestation"])
def test_any_failure_exits_non_zero(store, capsys, verb):
    r = Runner(cosign_fail={(verb, f"ghcr.io/devopssquaddev/zelkor-mcp@{DIGEST_MCP}")})
    assert _verify(store, r) == 1
    out = capsys.readouterr().out
    assert "FAIL" in out and "zelkor-mcp" in out


def test_missing_cosign_is_a_clear_error(store, capsys, monkeypatch):
    monkeypatch.setattr(verify_cmd.shutil, "which", lambda name: None)
    r = Runner()
    assert _verify(store, r) == 1
    err = capsys.readouterr().err
    assert "cosign" in err and "install" in err.lower()
    assert not r.cosign_calls()


def test_unknown_release_fails(store, capsys):
    assert _verify(store, Runner(helm_rc=1)) == 1
    assert "zp" in capsys.readouterr().err


def test_no_zelkor_images_fails_closed(store, capsys):
    pods = {"items": [_pod("lf", [("langfuse/langfuse:4.76.0", f"docker.io/langfuse/langfuse@{DIGEST_LF}")])]}
    assert _verify(store, Runner(pods=pods)) == 1
    assert "no Zelkor images" in capsys.readouterr().err


def test_image_without_resolved_digest_is_verified_by_tag_with_warning(store, capsys):
    pods = {"items": [_pod("m", [("ghcr.io/devopssquaddev/zelkor-mcp:2.4.6", "")])]}
    r = Runner(pods=pods)
    assert _verify(store, r) == 0
    assert {c[-1] for c in r.cosign_calls()} == {"ghcr.io/devopssquaddev/zelkor-mcp:2.4.6"}
    assert "no digest" in capsys.readouterr().out


def test_digest_pinned_spec_is_kept():
    ref = verify_cmd.verify_ref(f"ghcr.io/devopssquaddev/zelkor-mcp@{DIGEST_MCP}", "")
    assert ref == f"ghcr.io/devopssquaddev/zelkor-mcp@{DIGEST_MCP}"
    ref = verify_cmd.verify_ref("ghcr.io/devopssquaddev/zelkor-mcp:2.4.6",
                                f"docker-pullable://ghcr.io/devopssquaddev/zelkor-mcp@{DIGEST_MCP}")
    assert ref == f"ghcr.io/devopssquaddev/zelkor-mcp@{DIGEST_MCP}"


def test_cosign_timeout_is_a_failed_check_not_a_crash(store, capsys):
    mcp = f"ghcr.io/devopssquaddev/zelkor-mcp@{DIGEST_MCP}"
    r = Runner(cosign_timeout={("verify", mcp)})
    assert _verify(store, r) == 1
    out = capsys.readouterr().out
    assert f"FAIL signature  {mcp}" in out and "timed out after 120s" in out
    assert "3/4 checks passed" in out  # the other checks still ran


def test_env_after_the_command_overrides_the_global_flag(store):
    r = Runner()
    assert main(["--store", str(store), "verify", "zp", "--env", "lab"], runner=r) == 0
    kube = next(c for c in r.calls if c[0] == "kubectl")
    assert "kind-zelkor" in kube


def test_digest_pinned_pod_with_bare_status_image_is_verified(store, capsys):
    """containerd (k3s) reports status.image as the config digest when the spec pins a digest;
    the repository comes from the pod spec, so the image is still verified (it was skipped)."""
    pinned = f"ghcr.io/devopssquaddev/zelkor-aegra@{DIGEST_AEGRA}"
    pod = {"metadata": {"name": "zp-aegra-0"},
           "spec": {"containers": [{"name": "aegra", "image": pinned}]},
           "status": {"containerStatuses": [{"name": "aegra", "image": "sha256:" + "9" * 64,
                                             "imageID": pinned}]}}
    r = Runner(pods={"items": [pod]})
    assert _verify(store, r) == 0
    assert sorted({c[-1] for c in r.cosign_calls()}) == [pinned]
    assert "2/2 checks passed for 1 Zelkor image(s)" in capsys.readouterr().out


def test_bare_status_image_without_spec_falls_back_to_image_id():
    from zelkor.verify_cmd import _image_name

    ref = f"ghcr.io/devopssquaddev/zelkor-mcp@{DIGEST_MCP}"
    assert _image_name("", "sha256:" + "9" * 64, ref) == ref
    assert _image_name("", "sha256:" + "9" * 64, "docker-pullable://" + ref) == ref
    assert _image_name("ghcr.io/devopssquaddev/zelkor-mcp:2.5.5", "sha256:" + "9" * 64, ref) == \
        "ghcr.io/devopssquaddev/zelkor-mcp:2.5.5"
