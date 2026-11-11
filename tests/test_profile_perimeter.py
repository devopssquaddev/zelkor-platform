"""CE-15a: profile=perimeter renders the zero-DB egress boundary (offline helm template)."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "charts" / "zelkor-platform"
LOCAL_PERIMETER = ROOT / "profiles" / "values-local-perimeter.yaml"
THIN_PERIMETER = ROOT / "profiles" / "values-perimeter.yaml"
LOCAL_FAST = ROOT / "profiles" / "values-local-fast.yaml"

# A provider credential so the AIGatewayRoute renders; the overlay supplies hosts and signing.
PROVIDER = ("--set", "workspace.models.providers.openai.apiKey=sk-test")

# Workloads that must NOT appear in a zero-DB perimeter (matched against Deployment/StatefulSet names).
ABSENT_WORKLOADS = [
    "postgresql", "clickhouse", "valkey", "qdrant", "seaweedfs",
    "langfuse", "aegra", "nemo",
    "mcp-postgres", "mcp-qdrant", "mcp-sandbox",
]


def _helm(*extra: str) -> subprocess.CompletedProcess[str]:
    cmd = ["helm", "template", "zelkor-platform", str(CHART), "--namespace", "zelkor", *extra]
    return subprocess.run(cmd, check=False, capture_output=True, text=True)


def _docs(rendered: str) -> list[dict]:
    return [d for d in yaml.safe_load_all(rendered) if d]


def _named(docs: list[dict], kind: str, substring: str) -> dict | None:
    for doc in docs:
        if doc.get("kind") == kind and substring in doc.get("metadata", {}).get("name", ""):
            return doc
    return None


def _workload_names(docs: list[dict]) -> set[str]:
    return {
        d["metadata"]["name"]
        for d in docs
        if d.get("kind") in ("Deployment", "StatefulSet")
    }


def test_perimeter_disables_every_stateful_workload():
    proc = _helm("-f", str(LOCAL_PERIMETER), *PROVIDER)
    assert proc.returncode == 0, proc.stderr
    names = _workload_names(_docs(proc.stdout))
    for token in ABSENT_WORKLOADS:
        assert not any(token in n for n in names), f"{token} should not render in perimeter: {names}"


def test_perimeter_keeps_the_boundary():
    docs = _docs(_helm("-f", str(LOCAL_PERIMETER), *PROVIDER).stdout)
    assert _named(docs, "Gateway", "-gateway") is not None
    assert _named(docs, "GatewayClass", "eg") is not None
    assert _named(docs, "MCPRoute", "-mcp") is not None
    assert _named(docs, "Deployment", "mcp-aigateway") is not None
    assert _named(docs, "NetworkPolicy", "default-deny-ingress") is not None
    assert _named(docs, "BackendTrafficPolicy", "aigateway-ratelimit") is not None


def test_perimeter_mcproute_defaults_to_deny():
    docs = _docs(_helm("-f", str(LOCAL_PERIMETER), *PROVIDER).stdout)
    route = _named(docs, "MCPRoute", "-mcp")
    assert route is not None
    assert '"defaultAction": "Deny"' in json.dumps(route), route


def test_profile_flag_overrides_a_full_config():
    # The raw --set profile=perimeter must win over a complete (full) overlay — the
    # ArtifactHub one-liner path: strip the stateful planes from an otherwise full install.
    proc = _helm("-f", str(LOCAL_FAST), "--set", "profile=perimeter")
    assert proc.returncode == 0, proc.stderr
    names = _workload_names(_docs(proc.stdout))
    for token in ("postgresql", "langfuse", "aegra"):
        assert not any(token in n for n in names), f"{token} should be stripped: {names}"


def test_thin_overlay_only_sets_profile():
    data = yaml.safe_load(THIN_PERIMETER.read_text())
    assert data == {"profile": "perimeter"}


def test_unknown_profile_is_rejected():
    proc = _helm("-f", str(LOCAL_PERIMETER), "--set", "profile=bogus")
    assert proc.returncode != 0


def test_default_profile_still_renders_datastores():
    docs = _docs(_helm("-f", str(LOCAL_FAST)).stdout)
    assert _named(docs, "StatefulSet", "postgresql") is not None
