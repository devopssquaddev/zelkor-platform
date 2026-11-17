"""zelkor verify <release> — check that every running Zelkor image is a signed CE release.

For each first-party image in the release's running pods: `cosign verify` (keyless signature) and
`cosign verify-attestation --type slsaprovenance1` (SLSA provenance), both bound to the release
workflow identity below. Upstream images (Langfuse, datastores) are listed, not verified here:
their digests are in the signed release attestation on the platform chart.
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
import sys
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Callable

# One place each in the CLI; tests assert they equal charts/zelkor-platform values
# security.imageVerification.keyless.{issuer,subjectRegExp}.
SIGSTORE_ISSUER = "https://token.actions.githubusercontent.com"
RELEASE_IDENTITY_REGEXP = (
    r"^https://github\.com/devopssquaddev/zelkor-platform/\.github/workflows/release\.yml"
    r"@refs/tags/v[0-9]+\.[0-9]+\.[0-9]+-ce$"
)
IMAGE_PREFIX = "ghcr.io/devopssquaddev/zelkor-"
PROVENANCE_TYPE = "slsaprovenance1"
COSIGN_INSTALL = "https://docs.sigstore.dev/cosign/system_config/installation/"
COSIGN_TIMEOUT_SEC = 120

logger = logging.getLogger("zelkor-cli")

RunFn = Callable[..., Any]


@dataclass(frozen=True)
class RunningImage:
    pod: str
    container: str
    image: str
    image_id: str


def verify_ref(image: str, image_id: str) -> str:
    """Digest reference to verify: the spec digest, else the digest the node resolved, else the tag."""
    if "@sha256:" in image:
        return image
    if "@sha256:" in image_id:
        digest = image_id.rsplit("@", 1)[1]
        repo = image.rsplit(":", 1)[0] if ":" in image.rsplit("/", 1)[-1] else image
        return f"{repo}@{digest}"
    return image


def _call(runner: RunFn, argv: list[str]) -> Any:
    """Run argv; a timeout is a failed check (rc 124, like timeout(1)), not a traceback."""
    try:
        return runner(argv, capture_output=True, text=True, check=False, timeout=COSIGN_TIMEOUT_SEC)
    except subprocess.TimeoutExpired:
        return SimpleNamespace(returncode=124, stdout="",
                               stderr=f"{argv[0]} {argv[1] if len(argv) > 1 else ''} timed out after {COSIGN_TIMEOUT_SEC}s")


def running_images(runner: RunFn, kubectl: list[str], release: str) -> list[RunningImage]:
    res = _call(runner, kubectl + ["get", "pods", "-l", f"app.kubernetes.io/instance={release}", "-o", "json"])
    if res.returncode != 0:
        raise RuntimeError(f"kubectl get pods failed: {(res.stderr or res.stdout or '').strip()}")
    out: list[RunningImage] = []
    for pod in (json.loads(res.stdout or "{}") or {}).get("items") or []:
        name = (pod.get("metadata") or {}).get("name", "")
        status = pod.get("status") or {}
        for cs in (status.get("initContainerStatuses") or []) + (status.get("containerStatuses") or []):
            out.append(RunningImage(name, cs.get("name", ""), cs.get("image", ""), cs.get("imageID", "")))
    return out


def _cosign_argv(verb: str, ref: str) -> list[str]:
    argv = ["cosign", verb, "--certificate-oidc-issuer", SIGSTORE_ISSUER,
            "--certificate-identity-regexp", RELEASE_IDENTITY_REGEXP]
    if verb == "verify-attestation":
        argv += ["--type", PROVENANCE_TYPE]
    return argv + [ref]


def _last_line(text: str) -> str:
    lines = [ln for ln in (text or "").strip().splitlines() if ln.strip()]
    return lines[-1] if lines else ""


def cmd_verify(release: str, namespace: str, *, kubectl: list[str], helm: list[str],
               runner: RunFn) -> int:
    logger.info("verify release=%s namespace=%s", release, namespace)
    if not shutil.which("cosign"):
        print(f"cosign not found on PATH; install it to verify signatures: {COSIGN_INSTALL}", file=sys.stderr)
        return 1
    status = _call(runner, helm + ["status", release, "-o", "json"])
    if status.returncode != 0:
        print(f"Helm release {release} not found in namespace {namespace}: "
              f"{_last_line(status.stderr or status.stdout)}", file=sys.stderr)
        return 1
    try:
        images = running_images(runner, kubectl, release)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    refs: dict[str, list[RunningImage]] = {}
    upstream: set[str] = set()
    for img in images:
        if img.image.startswith(IMAGE_PREFIX):
            refs.setdefault(verify_ref(img.image, img.image_id), []).append(img)
        elif img.image:
            upstream.add(img.image)
    if not refs:
        print(f"no Zelkor images running for release {release} in namespace {namespace}; nothing verified",
              file=sys.stderr)
        return 1

    failed = 0
    for ref in sorted(refs):
        where = ", ".join(sorted({f"{i.pod}/{i.container}" for i in refs[ref]}))
        if "@sha256:" not in ref:
            print(f"WARN {ref}: no digest resolved on the node; verifying the tag ({where})")
        for verb, label in (("verify", "signature"), ("verify-attestation", "provenance")):
            res = _call(runner, _cosign_argv(verb, ref))
            ok = res.returncode == 0
            logger.info("cosign %s %s rc=%s", verb, ref, res.returncode)
            print(f"{'PASS' if ok else 'FAIL'} {label:<10} {ref}")
            if not ok:
                failed += 1
                print(f"     {_last_line(res.stderr or res.stdout)} ({where})")
    for image in sorted(upstream):
        print(f"SKIP upstream   {image} (not signed by Zelkor; digest is in the release attestation)")
    total = 2 * len(refs)
    print(f"{total - failed}/{total} checks passed for {len(refs)} Zelkor image(s) in {namespace}/{release}")
    return 1 if failed else 0
