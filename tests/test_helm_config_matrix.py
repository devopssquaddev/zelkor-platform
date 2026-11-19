"""Config matrix: render every row of tests/config_matrix/matrix.tsv (PICT covering array).

Rows come from tests/config_matrix/model.pict. A customer combination the chart rejects
on purpose is a PICT constraint in the model, not a skipped row here.
"""
from __future__ import annotations

import csv
import re
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
    "platform.telemetry.langfuse.surfaces.llmConnection.enabled": "needs a seeded tenant; live only (Langfuse surfaces)",
    "gateway.enabled": "set by @gateway profile",
    "gateway.envoyProxy.enabled": "set by @gateway profile",
    "workspace.models.inClusterService.enabled": "internal wiring of workspace.models",
    "workspace.policies.nemo.aiGatewayRoute.enabled": "experimental NeMo AIGatewayRoute; no render test yet",
    "workspace.policies.nemo.observability.otel.enabled": "follows platform.telemetry.nemoOtel",
    "security.sandbox.provisioning.verify.enabled": "Job-only sub-switch of provisioning.mode",
    "databases.postgresql.barman.enabled": "needs object-store credentials; test_helm_operator_mode.py",
    "seaweedfs.persistence.enabled": "storage sizing, not a feature",
    "postgresql.persistence.enabled": "storage, not a feature; test_helm_postgres_persistence.py",
    "platform.telemetry.otlp.enabled": "no-op switch: otlp.endpoint decides (single-sink gate); test_profile_perimeter.py",
    # Security knobs that are not named enabled/mode (see SECURITY_KNOBS).
    "platform.isolation.agentNamespaces": "agent-namespace NetworkPolicies; test_network_policies.py",
    "security.sandbox.failClosed": "verify Job exit code only; test_s25_gvisor_fail_closed.py",
    "security.imageVerification.failureAction": "ClusterPolicy field; test_helm_image_verification.py",
    "security.imageVerification.requireProvenance": "ClusterPolicy attestation rule; test_helm_image_verification.py",
    "workspace.policies.nemo.selfCheck.input": "NeMo rail mode; test_helm_nemo_self_check_flows.py",
    "workspace.policies.nemo.selfCheck.output": "NeMo rail mode; test_helm_nemo_self_check_flows.py",
    "workspace.policies.nemo.selfCheck.onUnavailable": "NeMo rail mode; test_helm_nemo_self_check_flows.py",
    "workspace.tools.objectMCP.allowDelete": "object MCP tool list (env only); no render test yet",
}
# Booleans/enums that change rendered security objects but are not named enabled/mode/tier
# (coverage audit finding 49). Each must be modeled or EXCLUDED like any other toggle.
SECURITY_KNOBS = [
    "platform.isolation.agentNamespaces",
    "security.mcp.acceptUnprotectedBackends",
    "security.sandbox.failClosed",
    "security.imageVerification.failureAction",
    "security.imageVerification.requireProvenance",
    "gateway.envoyProxy.hostNetwork",
    "workspace.policies.nemo.selfCheck.input",
    "workspace.policies.nemo.selfCheck.output",
    "workspace.policies.nemo.selfCheck.onUnavailable",
    "workspace.tools.objectMCP.allowDelete",
]

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
    ("perimeter.dataTools.postgres", "true"): [
        "workspace.tools.postgresMCP.databaseUrlSecretRef.name=customer-db",
        "workspace.tools.postgresMCP.egressTo[0].namespace=customer-data",
        "workspace.tools.postgresMCP.egressTo[0].port=5432",
    ],
    ("perimeter.dataTools.qdrant", "true"): [
        "workspace.tools.qdrantMCP.url=http://qdrant.customer-data.svc:6333",
        "workspace.tools.qdrantMCP.egressTo[0].namespace=customer-data",
        "workspace.tools.qdrantMCP.egressTo[0].port=6333",
    ],
    ("workspace.tools.objectMCP.enabled", "true"): [
        "workspace.tools.objectMCP.s3.endpoint=https://s3.example.com",
        "workspace.tools.objectMCP.s3.bucket=zelkor-objects",
        "workspace.tools.objectMCP.s3.auth.accessKey=obj-ak",
        "workspace.tools.objectMCP.s3.auth.secretKey=obj-sk",
        "workspace.tools.objectMCP.s3.egressCIDRs[0]=198.51.100.0/24",
    ],
}

# Toggle off => no rendered object carries one of these zelkor.io/intent labels, or (kind, name part).
ABSENT_WHEN_OFF = {
    "postgresql.enabled": {"postgresql"},
    "security.dnsLockdown.enabled": {"security.dnsLockdown"},
    "workspace.tools.objectMCP.enabled": {"mcp.objectMCP"},
    "workspace.tools.enabled": {"mcp.postgres", "mcp.qdrant", "mcp.aigateway", "mcp.sandbox", "mcp.objectMCP"},
    "platform.telemetry.langfuse.worker.enabled": ("Deployment", "langfuse-worker"),
    "platform.telemetry.langfuse.publicHttpRoute.enabled": ("HTTPRoute", "langfuse-route"),
    "security.imageVerification.enabled": ("ClusterPolicy", "verify-images"),
    "security.sandbox.enabled": ("RuntimeClass", "gvisor"),
    "observability.serviceMonitor.enabled": ("ServiceMonitor", ""),
    "highAvailability.enabled": ("HorizontalPodAutoscaler", ""),
    "workspace.models.enabled": ("Secret", "ai-gateway-consumer"),
    "workspace.policies.nemo.intercept.enabled": ("Service", "ai-gateway-nemo"),
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
# Modeled *.enabled toggles whose "off" removes no object (they change fields or env); why.
NO_ABSENCE_ORACLE = {
    "security.networkPolicies.enabled": "the default-deny invariant in the row test",
    "gateway.tls.enabled": "Gateway HTTPS listener field, no object of its own",
    "security.sandbox.executionLog.enabled": "worker env only",
    "platform.telemetry.nemoOtel.enabled": "NeMo env only",
    "workspace.models.rateLimit.enabled": "BackendTrafficPolicy field; test_helm_ai_gateway_rate_limit.py",
    "workspace.policies.nemo.selfCheck.enabled": "NeMo config content; test_helm_nemo_self_check_flows.py",
    "workspace.tools.policy.rateLimit.enabled": "MCP env only; test_helm_mcp_tool_policy.py",
    "workload.agents.redisBroker.enabled": "Aegra env only",
    "workload.agents.graphModules.enabled": "Aegra ConfigMap content",
    "workload.agents.mcpInject.enabled": "Aegra env only",
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

    for toggle, absent in ABSENT_WHEN_OFF.items():
        if row.get(toggle) != "false":
            continue
        if isinstance(absent, tuple):
            kind, part = absent
            leaked = sorted(d["metadata"]["name"] for d in docs if d.get("kind") == kind and part in d["metadata"]["name"])
        else:
            leaked = sorted({_intent(d) for d in docs} & absent)
        assert not leaked, f"{toggle}=false still renders {leaked}"

    # security.mcp floor policies render regardless of the opt-in; everything else follows it.
    opt_in = {d["metadata"]["name"] for d in docs if d.get("kind") == "NetworkPolicy" and _intent(d) != "security.mcp"}
    if row.get("profile") == "perimeter":
        # perimeter forces NetworkPolicies on; they render whenever the platform runs tool servers
        # (an LLM-only perimeter has none: wrapped agents bring their own policies)
        expected = row["workspace.tools.enabled"] == "true"
    else:
        expected = row["security.networkPolicies.enabled"] == "true"
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
    toggles = {*_value_toggles(yaml.safe_load(VALUES.read_text())), *SECURITY_KNOBS}
    missing = sorted(t for t in toggles if t not in modeled | EXCLUDED.keys())
    assert not missing, f"add to tests/config_matrix/model.pict or EXCLUDED with a reason: {missing}"


def test_security_knobs_exist_in_values():
    values = yaml.safe_load(VALUES.read_text())
    for knob in SECURITY_KNOBS:
        node = values
        for part in knob.split("."):
            assert isinstance(node, dict) and part in node, f"SECURITY_KNOBS entry {knob} is not in values.yaml"
            node = node[part]


def test_every_modeled_enabled_toggle_has_an_absence_oracle_or_reason():
    enabled = {p for p in _model_params() if p.endswith(".enabled")}
    missing = sorted(enabled - ABSENT_WHEN_OFF.keys() - NO_ABSENCE_ORACLE.keys())
    assert not missing, f"add to ABSENT_WHEN_OFF, or NO_ABSENCE_ORACLE with a reason: {missing}"


@pytest.mark.parametrize("table", ["EXCLUDED", "NO_ABSENCE_ORACLE"])
def test_reasons_that_name_a_test_point_at_a_test_that_sets_the_toggle(table):
    """Coverage audit finding 50: a cited test must exist and mention the toggle it vouches for."""
    tests_dir = Path(__file__).resolve().parent
    for toggle, reason in globals()[table].items():
        for name in re.findall(r"(test_\w+\.py)", reason):
            path = tests_dir / name
            assert path.is_file(), f"{toggle}: {name} does not exist"
            leaf = toggle.rsplit(".", 1)[-1] if toggle.rsplit(".", 1)[-1] not in ("enabled", "mode") else toggle.split(".")[-2]
            assert leaf in path.read_text(), f"{toggle}: {name} never mentions {leaf}"


def test_model_params_exist_in_values():
    values = yaml.safe_load(VALUES.read_text())
    for p in _model_params():
        if p.startswith("@"):
            continue
        node = values
        for part in p.split("."):
            assert isinstance(node, dict) and part in node, f"model parameter {p} is not in values.yaml"
            node = node[part]


def _tsv(text: str) -> tuple[list[str], list[list[str]]]:
    lines = [line.split("\t") for line in text.strip("\n").splitlines()]
    return lines[0], lines[1:]


def _coverage(header: list[str], rows: list[list[str]], params: list[str], k: int) -> set:
    from itertools import combinations

    idx = [header.index(p) for p in params]
    return {tuple((header[i], row[i]) for i in combo) for row in rows for combo in combinations(idx, k)}


def _sub_model() -> list[str]:
    for line in MODEL.read_text().splitlines():
        if line.strip().startswith("{") and "@" in line:
            return [p.strip() for p in line.split("{", 1)[1].split("}", 1)[0].split(",")]
    return []


@pytest.mark.skipif(shutil.which("pict") is None, reason="pict not installed")
def test_matrix_is_current_with_model():
    """The committed matrix covers exactly the combinations pict covers for the model: every valid
    pair, and every valid triple of the isolation sub-model. Row order and row count differ between
    pict builds (macOS vs Linux), so rows are not compared byte for byte."""
    out = subprocess.run(["pict", str(MODEL)], check=True, capture_output=True, text=True).stdout
    fresh_header, fresh = _tsv(out)
    header, committed = _tsv(MATRIX.read_text())
    hint = "regenerate: pict tests/config_matrix/model.pict > tests/config_matrix/matrix.tsv"
    assert header == fresh_header, f"parameters changed; {hint}"
    pairs_fresh, pairs = _coverage(header, fresh, header, 2), _coverage(header, committed, header, 2)
    assert pairs == pairs_fresh, (f"{len(pairs_fresh - pairs)} valid pairs uncovered, "
                                  f"{len(pairs - pairs_fresh)} pairs pict excludes; {hint}")
    sub = _sub_model()
    if sub:
        assert _coverage(header, committed, sub, 3) >= _coverage(header, fresh, sub, 3), f"3-way sub-model; {hint}"


def test_network_policies_without_agents_or_tools_fails_with_message():
    row = dict(_rows()[0])
    row.update({
        "profile": "full",
        "perimeter.guardrails": "false", "perimeter.sandbox": "false",
        "perimeter.dataTools.postgres": "false", "perimeter.dataTools.qdrant": "false",
        "security.networkPolicies.enabled": "true",
        "workload.agents.enabled": "false",
        "workspace.tools.enabled": "false",
    })
    r = _render(row)
    assert r.returncode != 0
    assert "security.networkPolicies.enabled requires workload.agents.enabled or workspace.tools.enabled" in r.stderr
