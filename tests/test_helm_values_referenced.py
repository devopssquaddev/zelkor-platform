"""CE-1 L2: every values.yaml leaf changes the render, or is allowlisted with a reason.

Cheap pass first: a leaf whose key is named in a template is assumed read. Every other leaf
(except resources/probes, which templates pass through whole with toYaml) is mutated and
rendered; if nothing but per-render random secrets and checksums changes, the key is dead.
"""
from __future__ import annotations

import json
import re
import subprocess

import pytest
import yaml

from tests.test_helm_config_matrix import COMPANIONS
from tests.test_helm_values_schema import CHART, SECRET_SETS

# key -> why it is kept although no template reads it
ALLOWED_DEAD = {
    # Deprecated in values.schema.json ("Deprecated: no effect"); kept so existing values files still validate.
    "workspace.tools.sandboxMCP.strictIsolation": "deprecated",
    "workspace.tools.sandboxMCP.environments": "deprecated",
    "workspace.policies.nemo.complianceRefusal": "deprecated",
    "platform.telemetry.langfuse.init.userName": "deprecated",
    "platform.telemetry.langfuse.init.userPassword": "deprecated",
    # Read outside the templates.
    "platform.tenants.jwt.localSigning.seedTokenTTL": "installer: scripts/lib/local-signing-helm-sets.sh mints the seed token",
}
DEPRECATED = {k for k, why in ALLOWED_DEAD.items() if why == "deprecated"}
PASSTHROUGH = re.compile(r"\.(resources|startupProbe|livenessProbe|readinessProbe)\.")
ON = ["workspace.tools.objectMCP.enabled=true", "security.sandbox.provisioning.mode=daemonset",
      *COMPANIONS[("workspace.tools.objectMCP.enabled", "true")]]


def _leaves(d, path=()):
    if isinstance(d, dict) and d:
        for k, v in d.items():
            yield from _leaves(v, (*path, str(k)))
    elif path:
        yield ".".join(path), d


def _render(*extra: str) -> list[str]:
    cmd = ["helm", "template", "zelkor-platform", str(CHART), "--namespace", "zelkor"]
    for item in [*SECRET_SETS, *ON]:
        cmd += ["--set", item]
    r = subprocess.run([*cmd, *extra], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-400:]
    return [line for line in r.stdout.splitlines() if "checksum/" not in line]


def _mutation(key: str, val) -> list[str]:
    if isinstance(val, bool):
        return ["--set", f"{key}={str(not val).lower()}"]
    if isinstance(val, int):
        return ["--set", f"{key}={val + 7}"]
    if isinstance(val, str):
        return ["--set-string", f"{key}={val}zz7"]
    return ["--set-json", f"{key}={json.dumps(['zz7'] if isinstance(val, list) else {'zz7': 'x'})}"]


def _candidates() -> list[tuple[str, object]]:
    src = "\n".join(p.read_text(errors="ignore") for p in (CHART / "templates").rglob("*") if p.is_file())
    values = yaml.safe_load((CHART / "values.yaml").read_text())
    return [(k, v) for k, v in _leaves(values)
            if not re.search(rf"\b{re.escape(k.rsplit('.', 1)[-1])}\b", src) and not PASSTHROUGH.search(f".{k}.")]


@pytest.fixture(scope="module")
def baseline() -> tuple[list[str], set[int]]:
    a, b = _render(), _render()
    assert len(a) == len(b)
    return a, {i for i, (x, y) in enumerate(zip(a, b)) if x != y}  # generated secrets differ per render


def _changes(base: tuple[list[str], set[int]], rendered: list[str]) -> bool:
    lines, noisy = base
    if len(rendered) != len(lines):
        return True
    return any(x != y for i, (x, y) in enumerate(zip(lines, rendered)) if i not in noisy)


@pytest.mark.parametrize("key,val", _candidates(), ids=lambda x: x if isinstance(x, str) else "")
def test_values_leaf_changes_the_render(baseline, key, val):
    try:
        rendered = _render(*_mutation(key, val))
    except AssertionError:
        return  # the chart rejects the mutated value: the key is validated, so it is read
    changed = _changes(baseline, rendered)
    if key in ALLOWED_DEAD:
        assert not changed, f"{key} is allowlisted as dead but changes the render; drop it from ALLOWED_DEAD"
        return
    assert changed, f"{key} has no effect on the render: wire it, or deprecate it in ALLOWED_DEAD with a reason"


def test_deprecated_keys_say_so_in_the_schema():
    schema = json.loads((CHART / "values.schema.json").read_text())
    for key in DEPRECATED:
        node = schema
        for part in key.split("."):
            node = node["properties"][part]
        assert (node.get("description") or "").startswith("Deprecated: no effect"), key
