"""kubectl argv from env (Path B: KUBECONFIG + KUBECONTEXT)."""
from __future__ import annotations

import os
import subprocess
from typing import Sequence


def kubectl_cmd(*args: str, namespace: str | None = None) -> list[str]:
    cmd = ["kubectl"]
    kubeconfig = os.environ.get("KUBECONFIG", "").strip()
    if kubeconfig:
        cmd.extend(["--kubeconfig", kubeconfig])
    context = (
        os.environ.get("KUBECONTEXT", "").strip()
        or os.environ.get("KUBE_CONTEXT", "").strip()
    )
    if context:
        cmd.extend(["--context", context])
    ns = namespace if namespace is not None else os.environ.get("ZELKOR_PLATFORM_NAMESPACE", "zelkor")
    if ns:
        cmd.extend(["-n", ns])
    cmd.extend(args)
    return cmd


def kubectl_run(
    args: Sequence[str],
    *,
    namespace: str | None = None,
    timeout: int = 30,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        kubectl_cmd(*args, namespace=namespace),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def platform_contract(namespace: str | None = None) -> dict[str, str]:
    """The platform's discovery contract (zelkor-platform-contract), or {} when unreachable/absent.

    Without KUBECONTEXT this never asks kubectl: the machine's default context is not a target.
    """
    import json

    if not (os.environ.get("KUBECONTEXT", "").strip() or os.environ.get("KUBE_CONTEXT", "").strip()):
        return {}
    try:
        res = kubectl_run(["get", "configmap", "zelkor-platform-contract", "-o", "json"], namespace=namespace)
    except subprocess.TimeoutExpired:
        return {}
    if res.returncode != 0:
        return {}
    return (json.loads(res.stdout or "{}") or {}).get("data") or {}


def secret_value(name: str, key: str, namespace: str | None = None) -> str:
    """One decoded key of a Secret, or "" when unreadable (live tests only)."""
    import base64

    if not (os.environ.get("KUBECONTEXT", "").strip() or os.environ.get("KUBE_CONTEXT", "").strip()):
        return ""
    res = kubectl_run(["get", "secret", name, "-o", f"jsonpath={{.data.{key}}}"], namespace=namespace)
    return base64.b64decode(res.stdout).decode() if res.returncode == 0 and res.stdout.strip() else ""


def consumer_key() -> str:
    """The agents' AI Gateway consumer key: env first, else the release's consumer Secret."""
    release = os.environ.get("ZELKOR_PLATFORM_RELEASE", "zelkor-platform")
    return (os.environ.get("AI_GATEWAY_API_KEY") or os.environ.get("ZELKOR_CONSUMER_KEY")
            or secret_value(f"{release}-ai-gateway-consumer", "agents"))
