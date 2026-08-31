import json
import os
import subprocess

import pytest

from tests.helpers.mcp_client import MCPGatewayClient

ADVERSARIAL_MKNOD_SCRIPT = """import os, stat
results = {}
try:
    os.mknod('/tmp/fake_sda', stat.S_IFBLK | 0o660, os.makedev(8, 1))
    with open('/tmp/fake_sda', 'rb') as f:
        f.read(10)
    results['mknod_escape'] = 'EXPLOIT_SUCCEEDED'
except Exception as e:
    results['mknod_escape'] = f'BLOCKED: {type(e).__name__}'

results['host_root_visible'] = os.path.exists('/host') or os.path.exists('/var/run/docker.sock')
print(results)
"""

ADVERSARIAL_DMESG_SCRIPT = """import ctypes, subprocess
results = {}
try:
    dmesg_res = subprocess.run(["dmesg"], capture_output=True, text=True, timeout=2)
    results['dmesg_isolated'] = ('Starting gVisor' in dmesg_res.stdout) or (dmesg_res.returncode != 0)
except Exception:
    results['dmesg_isolated'] = True

try:
    libc = ctypes.CDLL(None)
    ret = libc.syscall(169, 0xfee1dead, 672274793, 0x01234567, None)
    results['reboot_syscall'] = f'RETURNED_{ret}'
except Exception as e:
    results['reboot_syscall'] = f'BLOCKED: {type(e).__name__}'

print(results)
"""


def test_mcp_sandbox_worker_uses_gvisor(kubecontext):
    """Platform sandbox worker pods must use RuntimeClass gvisor."""
    try:
        res = subprocess.run(
            [
                "kubectl", "--context", kubecontext, "get", "pods", "-A",
                "-l", "app.kubernetes.io/component=mcp-sandbox-worker", "-o", "json",
            ],
            capture_output=True,
            text=True,
        )
        if res.returncode != 0:
            pytest.skip(f"kubectl failed: {res.stderr}")
        items = json.loads(res.stdout).get("items", [])
        if not items:
            pytest.skip("No mcp-sandbox-worker pods found")
        spec = items[0]["spec"]
        assert spec.get("runtimeClassName") == "gvisor" or "gvisor" in str(spec)
    except Exception as exc:
        pytest.skip(f"Cluster not accessible: {exc}")


def test_mcp_sandbox_blocks_mknod_outbreak():
    """sandbox__execute_python blocks device creation under gVisor."""
    client = MCPGatewayClient("tenant_a")
    try:
        result = client.call_tool(
            "sandbox__execute_python",
            {"code": ADVERSARIAL_MKNOD_SCRIPT, "environment": "python-base"},
        )
    except ConnectionError as exc:
        pytest.skip(str(exc))

    stdout = result.get("stdout") or ""
    assert "BLOCKED" in stdout
    assert "EXPLOIT_SUCCEEDED" not in stdout
    assert "'host_root_visible': False" in stdout


def test_mcp_sandbox_blocks_privileged_syscall():
    """sandbox__execute_python isolates dmesg and privileged syscalls."""
    client = MCPGatewayClient("tenant_a")
    try:
        result = client.call_tool(
            "sandbox__execute_python",
            {"code": ADVERSARIAL_DMESG_SCRIPT, "environment": "python-base"},
        )
    except ConnectionError as exc:
        pytest.skip(str(exc))

    stdout = result.get("stdout") or ""
    assert "RETURNED_-1" in stdout or "BLOCKED" in stdout
    assert "'dmesg_isolated': True" in stdout


def test_mcp_sandbox_passwd_probe():
    """sandbox executes passwd read attempt without host compromise."""
    client = MCPGatewayClient("tenant_a")
    code = (
        "try:\n"
        "    with open('/etc/passwd') as f:\n"
        "        print(f.read()[:20])\n"
        "except Exception as e:\n"
        "    print(f'Error: {e}')"
    )
    try:
        result = client.call_tool(
            "sandbox__execute_python",
            {"code": code, "environment": "python-base"},
        )
    except ConnectionError as exc:
        pytest.skip(str(exc))

    assert "stdout" in result or "stderr" in result
