"""Trusted bootstrap: run user Python and emit ZELKOR_SANDBOX_RESULT on stderr."""
from __future__ import annotations

import json
import os
import stat
import sys
import traceback
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from typing import Any, Dict, List, Optional

RESULT_PREFIX = "ZELKOR_SANDBOX_RESULT "


def parse_bootstrap_line(text: str) -> Optional[Dict[str, Any]]:
    for line in reversed((text or "").splitlines()):
        line = line.strip()
        if line.startswith(RESULT_PREFIX):
            payload = line[len(RESULT_PREFIX) :].strip()
            try:
                return json.loads(payload)
            except json.JSONDecodeError:
                return None
    return None


def _probe_mknod_device() -> Dict[str, Any]:
    import os as _os

    try:
        path = "/tmp/.zelkor_probe_dev"
        _os.mknod(path, stat.S_IFBLK | 0o660, _os.makedev(8, 99))
        with open(path, "rb") as handle:
            handle.read(1)
        return {"ok": False, "signal": "exploit", "exc_type": "", "errno": None}
    except OSError as exc:
        return {
            "ok": False,
            "signal": "denied",
            "exc_type": type(exc).__name__,
            "errno": exc.errno,
        }
    except Exception as exc:
        return {
            "ok": False,
            "signal": "error",
            "exc_type": type(exc).__name__,
            "errno": getattr(exc, "errno", None),
        }


def _probe_host_escape() -> Dict[str, Any]:
    import os as _os

    visible = _os.path.exists("/host") or _os.path.exists("/var/run/docker.sock")
    if visible:
        return {"ok": False, "signal": "exploit", "exc_type": "", "errno": None}
    return {"ok": True, "signal": "completed", "exc_type": "", "errno": None}


def _probe_passwd_read() -> Dict[str, Any]:
    import os as _os

    try:
        with open("/etc/passwd", "r", encoding="utf-8") as handle:
            handle.read(64)
        return {"ok": True, "signal": "completed", "exc_type": "", "errno": None}
    except OSError as exc:
        return {
            "ok": False,
            "signal": "denied",
            "exc_type": type(exc).__name__,
            "errno": exc.errno,
        }


def _probe_dmesg() -> Dict[str, Any]:
    import subprocess

    try:
        res = subprocess.run(["dmesg"], capture_output=True, text=True, timeout=2)
        isolated = ("Starting gVisor" in (res.stdout or "")) or res.returncode != 0
        if isolated:
            return {"ok": True, "signal": "completed", "exc_type": "", "errno": None}
        return {"ok": False, "signal": "denied", "exc_type": "", "errno": None}
    except Exception as exc:
        return {
            "ok": False,
            "signal": "denied",
            "exc_type": type(exc).__name__,
            "errno": getattr(exc, "errno", None),
        }


def _probe_reboot_syscall() -> Dict[str, Any]:
    import ctypes

    try:
        libc = ctypes.CDLL(None)
        ret = libc.syscall(169, 0xFEE1DEAD, 672274793, 0x01234567, None)
        if ret == 0:
            return {"ok": False, "signal": "exploit", "exc_type": "", "errno": None}
        return {"ok": True, "signal": "completed", "exc_type": "", "errno": None}
    except OSError as exc:
        return {
            "ok": False,
            "signal": "denied",
            "exc_type": type(exc).__name__,
            "errno": exc.errno,
        }
    except Exception as exc:
        return {
            "ok": False,
            "signal": "denied",
            "exc_type": type(exc).__name__,
            "errno": getattr(exc, "errno", None),
        }


_PROBE_RUNNERS = {
    "mknod_device": _probe_mknod_device,
    "host_escape": _probe_host_escape,
    "passwd_read": _probe_passwd_read,
    "dmesg_probe": _probe_dmesg,
    "reboot_syscall": _probe_reboot_syscall,
    "ctypes_privileged": _probe_reboot_syscall,
}


def _run_probes(static_probes: List[str]) -> Dict[str, Dict[str, Any]]:
    results: Dict[str, Dict[str, Any]] = {}
    for name in static_probes:
        runner = _PROBE_RUNNERS.get(name)
        if runner is None:
            continue
        results[name] = runner()
    return results


def _bootstrap_outcome(
    *,
    user_exc: Optional[BaseException],
    probe_results: Dict[str, Dict[str, Any]],
    exit_code: int,
) -> str:
    for probe in probe_results.values():
        if probe.get("signal") == "exploit":
            return "exploit"
    for probe in probe_results.values():
        if probe.get("signal") == "denied":
            return "denied"
    if user_exc is not None:
        if isinstance(user_exc, (PermissionError, OSError)):
            return "denied"
        return "error"
    if exit_code != 0:
        return "error"
    return "completed"


def run_user_code(code_path: str, static_probes: List[str]) -> Dict[str, Any]:
    user_stdout = StringIO()
    user_stderr = StringIO()
    user_exc: Optional[BaseException] = None
    exit_code = 0

    with open(code_path, "r", encoding="utf-8") as handle:
        source = handle.read()

    namespace: Dict[str, Any] = {"__name__": "__main__"}
    with redirect_stdout(user_stdout), redirect_stderr(user_stderr):
        try:
            exec(compile(source, code_path, "exec"), namespace, namespace)
        except SystemExit as exc:
            code = exc.code
            exit_code = int(code) if isinstance(code, int) else (1 if code else 0)
        except BaseException as exc:
            user_exc = exc
            exit_code = 1
            traceback.print_exc(file=user_stderr)

    probe_results = _run_probes(static_probes)
    outcome = _bootstrap_outcome(
        user_exc=user_exc,
        probe_results=probe_results,
        exit_code=exit_code,
    )

    errno_val: Optional[int] = None
    exc_type = ""
    if user_exc is not None:
        exc_type = type(user_exc).__name__
        errno_val = getattr(user_exc, "errno", None)
    else:
        for probe in probe_results.values():
            if probe.get("errno") is not None:
                errno_val = probe.get("errno")
                exc_type = str(probe.get("exc_type") or exc_type)
                break

    return {
        "outcome": outcome,
        "errno": errno_val,
        "exc_type": exc_type,
        "probe_results": probe_results,
        "static_probes": static_probes,
        "user_stdout": user_stdout.getvalue(),
        "user_stderr": user_stderr.getvalue(),
        "exit_code": exit_code,
    }


def emit_result(result: Dict[str, Any]) -> None:
    sys.stderr.write(RESULT_PREFIX + json.dumps(result, separators=(",", ":")) + "\n")
    sys.stderr.flush()


def main(argv: List[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        emit_result(
            {
                "outcome": "error",
                "errno": None,
                "exc_type": "ValueError",
                "probe_results": {},
                "static_probes": [],
                "user_stdout": "",
                "user_stderr": "missing code path",
                "exit_code": 1,
            }
        )
        return 1

    code_path = args[0]
    raw_probes = os.getenv("SANDBOX_STATIC_PROBES", "[]")
    try:
        static_probes = json.loads(raw_probes)
        if not isinstance(static_probes, list):
            static_probes = []
    except json.JSONDecodeError:
        static_probes = []

    result = run_user_code(code_path, [str(p) for p in static_probes])
    emit_result(result)
    return int(result.get("exit_code") or 0)


if __name__ == "__main__":
    raise SystemExit(main())
