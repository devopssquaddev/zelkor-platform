import json
import os
import subprocess

import pytest

PLATFORM_NAMESPACE = os.environ.get("ZELKOR_PLATFORM_NAMESPACE", "default")


def test_network_policies_present_when_enabled(kubecontext):
    """Path A overlay enables NetworkPolicies; skip when the flag is off."""
    try:
        res = subprocess.run(
            [
                "kubectl",
                "--context",
                kubecontext,
                "get",
                "networkpolicy",
                "-n",
                PLATFORM_NAMESPACE,
                "-o",
                "json",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        pytest.skip(str(exc))
    items = json.loads(res.stdout).get("items") or []
    names = [item["metadata"]["name"] for item in items]
    if not any("agent-egress" in n for n in names):
        pytest.skip("security.networkPolicies.enabled is off in this cluster")
    assert any("mcp-gateway-egress" in n for n in names), names
    assert any("sandbox-worker-ingress" in n for n in names), names
    assert any("aegra-egress" in n for n in names), names
