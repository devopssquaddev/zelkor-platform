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
