"""CE-19d: opt-in Kyverno admission policy that rejects unsigned or mismatched Zelkor images (L2)."""
from __future__ import annotations

import yaml

from tests.test_helm_values_schema import CHART, _docs, _helm

VALUES = yaml.safe_load((CHART / "values.yaml").read_text())
IV = VALUES["security"]["imageVerification"]
ISSUER = "https://token.actions.githubusercontent.com"
IDENTITY_RE = (r"^https://github\.com/devopssquaddev/zelkor-platform/\.github/workflows/release\.yml"
               r"@refs/tags/v[0-9]+\.[0-9]+\.[0-9]+-ce$")


def _policies(*extra: str) -> list[dict]:
    r = _helm(*extra)
    assert r.returncode == 0, r.stderr
    return [d for d in _docs(r.stdout) if d and d.get("kind") == "ClusterPolicy"]


def test_off_by_default():
    assert IV["enabled"] is False
    assert _policies() == []


def test_values_carry_the_release_identity():
    assert IV["keyless"]["issuer"] == ISSUER
    assert IV["keyless"]["subjectRegExp"] == IDENTITY_RE
    assert IV["images"] == ["ghcr.io/devopssquaddev/zelkor-*"]


def test_enabled_renders_enforcing_keyless_policy():
    [pol] = _policies("--set", "security.imageVerification.enabled=true")
    assert pol["apiVersion"] == "kyverno.io/v1"
    assert pol["metadata"]["labels"]["zelkor.io/intent"] == "security"
    spec = pol["spec"]
    assert spec["validationFailureAction"] == "Enforce"
    assert spec["background"] is False
    assert spec["failurePolicy"] == "Fail"
    [rule] = spec["rules"]
    assert rule["match"]["any"][0]["resources"]["kinds"] == ["Pod"]
    [vi] = rule["verifyImages"]
    assert vi["imageReferences"] == ["ghcr.io/devopssquaddev/zelkor-*"]
    assert vi["mutateDigest"] is True and vi["verifyDigest"] is True and vi["required"] is True
    keyless = vi["attestors"][0]["entries"][0]["keyless"]
    assert keyless["issuer"] == ISSUER
    assert keyless["subjectRegExp"] == IDENTITY_RE
    assert keyless["rekor"]["url"] == "https://rekor.sigstore.dev"


def test_provenance_attestation_names_repo_and_workflow():
    [pol] = _policies("--set", "security.imageVerification.enabled=true")
    [att] = pol["spec"]["rules"][0]["verifyImages"][0]["attestations"]
    assert att["type"] == "https://slsa.dev/provenance/v1"
    assert att["attestors"][0]["entries"][0]["keyless"]["subjectRegExp"] == IDENTITY_RE
    conds = {c["key"]: c["value"] for c in att["conditions"][0]["all"]}
    assert conds["{{ buildDefinition.externalParameters.workflow.repository }}"] == \
        "https://github.com/devopssquaddev/zelkor-platform"
    assert conds["{{ buildDefinition.externalParameters.workflow.path }}"] == ".github/workflows/release.yml"


def test_provenance_can_be_dropped_and_audit_mode_set():
    [pol] = _policies("--set", "security.imageVerification.enabled=true",
                      "--set", "security.imageVerification.requireProvenance=false",
                      "--set", "security.imageVerification.failureAction=Audit")
    assert pol["spec"]["validationFailureAction"] == "Audit"
    assert "attestations" not in pol["spec"]["rules"][0]["verifyImages"][0]


def test_namespaces_scope_the_match():
    [pol] = _policies("--set", "security.imageVerification.enabled=true",
                      "--set", "security.imageVerification.namespaces[0]=zelkor",
                      "--set", "security.imageVerification.namespaces[1]=agents")
    res = pol["spec"]["rules"][0]["match"]["any"][0]["resources"]
    assert res["namespaces"] == ["zelkor", "agents"]


def test_policy_name_is_release_scoped():
    [pol] = _policies("--set", "security.imageVerification.enabled=true")
    assert pol["metadata"]["name"] == "zelkor-platform-verify-images"


def test_bad_failure_action_fails_schema():
    r = _helm("--set", "security.imageVerification.enabled=true",
              "--set", "security.imageVerification.failureAction=Warn")
    assert r.returncode != 0


def test_empty_identity_fails_render():
    r = _helm("--set", "security.imageVerification.enabled=true",
              "--set", "security.imageVerification.keyless.subjectRegExp=")
    assert r.returncode != 0
    assert "security.imageVerification.keyless.subjectRegExp" in r.stderr
