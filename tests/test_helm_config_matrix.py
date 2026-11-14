"""Config matrix: render every row of tests/config_matrix/matrix.tsv (PICT covering array).

Rows come from tests/config_matrix/model.pict. A customer combination the chart rejects
on purpose is a PICT constraint in the model, not a skipped row here.
"""
from __future__ import annotations

import csv
import shutil
import subprocess
from collections import Counter
from pathlib import Path

import pytest
import yaml

from tests.test_helm_values_schema import CHART, PROFILES, SECRET_SETS, _docs

MATRIX_DIR = Path(__file__).resolve().parent / "config_matrix"
MODEL = MATRIX_DIR / "model.pict"
MATRIX = MATRIX_DIR / "matrix.tsv"
VALUES = CHART / "values.yaml"

# Toggles deliberately outside the model. Every other *.enabled / *.mode in values.yaml must be a model parameter.
EXCLUDED = {
    "global.tier": "CE chart accepts only oss; tier gates in test_helm_values_schema.py",
    "platform.mTLS.enabled": "Enterprise tier gate",
    "platform.tenants.sso.enabled": "Pro tier gate",
    "workload.intent.approval.enabled": "Pro tier gate",
    "security.mTLS.enabled": "Enterprise tier gate",
    "platform.tenants.jwt.localSigning.enabled": "installer-managed JWKS; covered by lab profiles",
    "platform.telemetry.langfuse.init.enabled": "installer-managed seed keys",
    "platform.telemetry.langfuse.admin.enabled": "always on; needs admin email set by installer",
    "platform.telemetry.langfuse.surfaces.llmConnection.enabled": "needs seeded tenant; test_langfuse_surfaces.py",
    "gateway.enabled": "set by @gateway profile",
    "gateway.envoyProxy.enabled": "set by @gateway profile",
    "workspace.models.inClusterService.enabled": "internal wiring of workspace.models",
    "workspace.policies.nemo.aiGatewayRoute.enabled": "experimental route; test_helm_nemo_self_check_flows.py",
    "workspace.policies.nemo.observability.otel.enabled": "follows platform.telemetry.nemoOtel",
    "security.sandbox.provisioning.verify.enabled": "Job-only sub-switch of provisioning.mode",
    "databases.postgresql.barman.enabled": "needs object-store credentials; test_helm_ce4_production.py",
    "seaweedfs.persistence.enabled": "storage sizing, not a feature",
}

# Values a toggle needs to be valid at all (what a customer must also set), not test fixtures.
COMPANIONS = {
    ("@gateway", "shared"): [
        "gateway.parentRef.name=customer-gateway",
        "gateway.parentRef.namespace=gateway-system",
        "gateway.mcproute.sharedGatewayAck=true",
        "workspace.models.inClusterService.targetHost=envoy-customer-gateway.gateway-system.svc.cluster.local",
    ],
    ("databases.mode", "external"): [
        "databases.postgresql.external.host=pg.example.internal",
        "databases.postgresql.external.username=zelkor",
        "databases.postgresql.external.password=test-pg",
        "databases.clickhouse.external.host=ch.example.internal",
        "databases.clickhouse.external.username=zelkor",
        "databases.clickhouse.external.password=test-ch",
        "databases.valkey.external.host=valkey.example.internal",
    ],
    ("workspace.tools.objectMCP.enabled", "true"): [
        "workspace.tools.objectMCP.s3.endpoint=https://s3.example.com",
        "workspace.tools.objectMCP.s3.bucket=zelkor-objects",
        "workspace.tools.objectMCP.s3.auth.accessKey=obj-ak",
        "workspace.tools.objectMCP.s3.auth.secretKey=obj-sk",
        "workspace.tools.objectMCP.s3.egressCIDRs[0]=198.51.100.0/24",
    ],
}

# Toggle off => no rendered object carries one of these zelkor.io/intent labels.
ABSENT_WHEN_OFF = {
    "valkey.enabled": {"valkey"},
    "clickhouse.enabled": {"clickhouse"},
    "qdrant.enabled": {"qdrant"},
    "seaweedfs.enabled": {"seaweedfs"},
    "workload.agents.enabled": {"aegra"},
    "platform.telemetry.langfuse.enabled": {"langfuse"},
    "workspace.policies.nemo.enabled": {"guardrails.nemo"},
    "workspace.tools.postgresMCP.enabled": {"mcp.postgres", "mcp.postgresMCP"},
    "workspace.tools.qdrantMCP.enabled": {"mcp.qdrant", "mcp.qdrantMCP"},
    "workspace.tools.aigatewayMCP.enabled": {"mcp.aigateway", "mcp.aigatewayMCP"},
    "workspace.tools.sandboxMCP.enabled": {"mcp.sandbox", "mcp.sandboxMCP"},
}

_BASE_SETS = [s for s in SECRET_SETS if not s.startswith("gateway.envoyProxy.")]


def _rows() -> list[dict[str, str]]:
    with MATRIX.open(newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def _render(row: dict[str, str]) -> subprocess.CompletedProcess[str]:
    cmd = ["helm", "template", "zelkor-platform", str(CHART), "--namespace", "zelkor"]
    for s in _BASE_SETS:
        cmd += ["--set", s]
    cmd += ["-f", str(PROFILES / f"values-gateway-{row['@gateway']}.yaml")]
    for key, value in row.items():
        if not key.startswith("@"):
            cmd += ["--set", f"{key}={value}"]
        for s in COMPANIONS.get((key, value), []):
            cmd += ["--set", s]
    return subprocess.run(cmd, check=False, capture_output=True, text=True)


def _intent(doc: dict) -> str:
    return ((doc.get("metadata") or {}).get("labels") or {}).get("zelkor.io/intent", "")


@pytest.mark.parametrize("row", [pytest.param(r, id=f"row{i}") for i, r in enumerate(_rows(), 1)])
def test_matrix_row_renders_and_holds_invariants(row):
    r = _render(row)
    assert r.returncode == 0, r.stderr
    docs = [d for d in _docs(r.stdout) if d]

    keys = Counter(
        (d.get("apiVersion"), d.get("kind"), d["metadata"].get("namespace", "zelkor"), d["metadata"]["name"])
        for d in docs
    )
    assert not [k for k, n in keys.items() if n > 1], "duplicate objects"

    for toggle, intents in ABSENT_WHEN_OFF.items():
        if row[toggle] == "false":
            leaked = sorted({_intent(d) for d in docs} & intents)
            assert not leaked, f"{toggle}=false still renders {leaked}"

    # security.mcp floor policies render regardless of the opt-in; everything else follows it.
    opt_in = {d["metadata"]["name"] for d in docs if d.get("kind") == "NetworkPolicy" and _intent(d) != "security.mcp"}
    expected = row["security.networkPolicies.enabled"] == "true" and "true" in (
        row["workload.agents.enabled"],
        row["workspace.tools.enabled"],
    )
    assert ("zelkor-platform-default-deny-ingress" in opt_in) == expected, sorted(opt_in)
    if not expected:
        assert not opt_in, sorted(opt_in)


def _model_params() -> list[str]:
    params = []
    for line in MODEL.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith(("#", "{", "IF")) and ":" in line:
            params.append(line.split(":", 1)[0].strip())
    return params


def _value_toggles(node, path=""):
    if isinstance(node, dict):
        for k, v in node.items():
            p = f"{path}.{k}" if path else k
            if k in ("enabled", "mode", "tier") and not isinstance(v, (dict, list)):
                yield p
            yield from _value_toggles(v, p)


def test_every_values_toggle_is_modeled_or_excluded():
    modeled = set(_model_params())
    missing = sorted(t for t in _value_toggles(yaml.safe_load(VALUES.read_text())) if t not in modeled | EXCLUDED.keys())
    assert not missing, f"add to tests/config_matrix/model.pict or EXCLUDED with a reason: {missing}"


def test_model_params_exist_in_values():
    values = yaml.safe_load(VALUES.read_text())
    for p in _model_params():
        if p.startswith("@"):
            continue
        node = values
        for part in p.split("."):
            assert isinstance(node, dict) and part in node, f"model parameter {p} is not in values.yaml"
            node = node[part]


@pytest.mark.skipif(shutil.which("pict") is None, reason="pict not installed")
def test_matrix_is_current_with_model():
    out = subprocess.run(["pict", str(MODEL)], check=True, capture_output=True, text=True).stdout
    assert out == MATRIX.read_text(), "regenerate: pict tests/config_matrix/model.pict > tests/config_matrix/matrix.tsv"
