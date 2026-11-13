"""The kind lab overlays stay one lab: settings shared by every profile are identical.

Each overlay is self-contained (scripts, docs and hooks pass exactly one `-f`), so shared
settings are duplicated on purpose; this test is what keeps the copies from drifting.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

PROFILES = Path(__file__).resolve().parents[1] / "profiles"
OVERLAYS = ("values-local.yaml", "values-local-fast.yaml", "values-local-perimeter.yaml")

# Dotted paths every lab overlay must set identically (the lab, not the profile).
SHARED = (
    "global",
    "security.mcp.acceptUnprotectedBackends",
    "gateway.enabled",
    "gateway.gatewayClassName",
    "gateway.envoyProxy",
    "gateway.hosts.agents",
    "gateway.hosts.aiGateway",
    "gateway.hosts.mcp",
    "platform.tenants",
    "platform.telemetry.format",
    "workspace.models.consumerKey",
    "workspace.models.rateLimit",
    "workspace.models.providers",
    "workspace.tools.enabled",
    "workspace.tools.policy.rateLimit",
)


def _get(data: dict, dotted: str):
    for part in dotted.split("."):
        if not isinstance(data, dict) or part not in data:
            return KeyError(dotted)
        data = data[part]
    return data


@pytest.mark.parametrize("path", SHARED)
def test_lab_overlays_share_common_settings(path):
    values = {name: _get(yaml.safe_load((PROFILES / name).read_text()), path) for name in OVERLAYS}
    missing = [n for n, v in values.items() if isinstance(v, KeyError)]
    assert not missing, f"{path} missing in {missing}"
    first = values[OVERLAYS[0]]
    assert all(v == first for v in values.values()), f"{path} drifted: {values}"
