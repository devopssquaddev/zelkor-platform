"""Classify sandbox Python runs for structured operational logs (no full code at INFO)."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

try:
    from sandbox.bootstrap_runner import RESULT_PREFIX, parse_bootstrap_line
except ImportError:
    from bootstrap_runner import RESULT_PREFIX, parse_bootstrap_line  # noqa: F401

_PREVIEW_LEN = 180

_CODE_PROBE_PATTERNS: Tuple[Tuple[str, re.Pattern[str]], ...] = (
    ("mknod_device", re.compile(r"\b(mknod|makedev)\b", re.I)),
    ("dmesg_probe", re.compile(r"\bdmesg\b|subprocess\.(run|call|Popen).*dmesg", re.I)),
    ("reboot_syscall", re.compile(r"\bsyscall\s*\(\s*169\b|reboot_syscall", re.I)),
    ("passwd_read", re.compile(r"/etc/passwd", re.I)),
    ("host_escape", re.compile(r"/host\b|docker\.sock", re.I)),
    ("ctypes_privileged", re.compile(r"\bctypes\b.*\bsyscall\b", re.I)),
)

_BLOCKED_RE = re.compile(r"BLOCKED:\s*([A-Za-z_][A-Za-z0-9_]*)")
_HOST_VISIBLE_RE = re.compile(r"""['"]host_root_visible['"]\s*:\s*True\b""")


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def execution_log_enabled() -> bool:
    return _env_bool("SANDBOX_EXECUTION_LOG_ENABLED", True)


def include_stdout_preview() -> bool:
    return _env_bool("SANDBOX_INCLUDE_STDOUT_PREVIEW", True)


def suspicious_on_probe_plus_error() -> bool:
    return _env_bool("SANDBOX_SUSPICIOUS_ON_PROBE_PLUS_ERROR", True)


@dataclass(frozen=True)
class ExecutionReport:
    outcome: str  # allowed | denied | suspicious | exploit | error | timeout
    exit_code: int
    violation_types: Tuple[str, ...]
    code_probes: Tuple[str, ...]
    code_fingerprint: str
    code_lines: int
    stdout_preview: str
    stderr_preview: str
    errno: Optional[int] = None
    exc_type: str = ""

    @property
    def violation_label(self) -> str:
        if self.violation_types:
            return ",".join(self.violation_types)
        return "none"

    @property
    def probes_label(self) -> str:
        if self.code_probes:
            return ",".join(self.code_probes)
        return "none"

    def to_execution_dict(self) -> Dict[str, Any]:
        return {
            "outcome": self.outcome,
            "violation": self.violation_label,
            "violations": list(self.violation_types),
            "errno": self.errno,
            "exc_type": self.exc_type or None,
            "code_sha": self.code_fingerprint,
            "probes": list(self.code_probes),
            "exit_code": self.exit_code,
        }


def _fingerprint(code: str) -> str:
    digest = hashlib.sha256(code.encode("utf-8")).hexdigest()
    return digest[:12]


def _strip_bootstrap_lines(text: str) -> str:
    kept: List[str] = []
    for line in (text or "").splitlines():
        if line.strip().startswith(RESULT_PREFIX):
            continue
        kept.append(line)
    return "\n".join(kept)


def _preview(text: str) -> str:
    if not include_stdout_preview():
        return ""
    collapsed = " ".join(_strip_bootstrap_lines(text or "").split())
    if len(collapsed) <= _PREVIEW_LEN:
        return collapsed
    return collapsed[: _PREVIEW_LEN - 3] + "..."


def detect_code_probes(code: str) -> Tuple[str, ...]:
    found: List[str] = []
    for name, pattern in _CODE_PROBE_PATTERNS:
        if pattern.search(code or ""):
            found.append(name)
    return tuple(found)


def _errno_name(errno_val: Optional[int]) -> str:
    if errno_val is None:
        return ""
    try:
        import errno as errno_mod

        for name in dir(errno_mod):
            if name.startswith("E") and getattr(errno_mod, name, None) == errno_val:
                return name
    except Exception:
        pass
    return str(errno_val)


def _violation_from_errno_probe(
    errno_val: Optional[int],
    exc_type: str,
    probes: Tuple[str, ...],
    probe_results: Dict[str, Any],
) -> Tuple[str, ...]:
    violations: List[str] = []
    errno_label = _errno_name(errno_val)
    lowered_exc = (exc_type or "").lower()

    if "mknod_device" in probes or "mknod_device" in probe_results:
        if errno_val == 1 or "perm" in lowered_exc or probe_results.get("mknod_device", {}).get("signal") == "denied":
            violations.append("permission_denied_mknod")
        elif errno_val is not None or exc_type:
            violations.append("permission_denied")

    for probe_name, result in probe_results.items():
        if not isinstance(result, dict):
            continue
        signal = result.get("signal")
        if signal == "exploit":
            if probe_name == "host_escape":
                violations.append("host_root_visible")
            elif probe_name == "mknod_device":
                violations.append("exploit_succeeded")
            else:
                violations.append(f"exploit_{probe_name}")
        elif signal == "denied":
            if probe_name == "dmesg_probe":
                violations.append("dmesg_not_isolated")
            elif probe_name == "reboot_syscall" and result.get("ok") is False:
                violations.append("syscall_denied")
            elif probe_name not in ("mknod_device",):
                violations.append(f"denied_{probe_name}")

    if errno_val is not None and not violations:
        if errno_label:
            violations.append(f"errno_{errno_label.lower()}")
        else:
            violations.append("permission_denied")
    elif exc_type and "permission" in lowered_exc and not violations:
        violations.append("permission_denied")

    seen: set[str] = set()
    out: List[str] = []
    for item in violations:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return tuple(out)


def _blocked_violation(blob: str, blocked_type: str) -> str:
    lowered = blocked_type.lower()
    if "permission" in lowered:
        if "mknod" in blob.lower() or "makedev" in blob.lower():
            return "permission_denied_mknod"
        return "permission_denied"
    if "timeout" in lowered:
        return "execution_timeout"
    return f"blocked_{lowered}"


def detect_output_violations(stdout: str, stderr: str) -> Tuple[str, ...]:
    blob = f"{stdout or ''}\n{stderr or ''}"
    violations: List[str] = []
    if "EXPLOIT_SUCCEEDED" in blob:
        violations.append("exploit_succeeded")
    for match in _BLOCKED_RE.finditer(blob):
        violations.append(_blocked_violation(blob, match.group(1)))
    if _HOST_VISIBLE_RE.search(blob):
        violations.append("host_root_visible")
    if "'dmesg_isolated': False" in blob or '"dmesg_isolated": false' in blob.lower():
        violations.append("dmesg_not_isolated")
    if "RETURNED_0" in blob and "reboot_syscall" in blob:
        violations.append("reboot_syscall_allowed")
    seen: set[str] = set()
    out: List[str] = []
    for v in violations:
        if v not in seen:
            seen.add(v)
            out.append(v)
    return tuple(out)


def _map_bootstrap_outcome(raw: str) -> str:
    mapping = {
        "completed": "allowed",
        "denied": "denied",
        "exploit": "exploit",
        "error": "error",
        "timeout": "timeout",
    }
    return mapping.get(raw, raw)


def _bootstrap_has_error_signal(bootstrap: Dict[str, Any]) -> bool:
    if bootstrap.get("errno") is not None:
        return True
    if bootstrap.get("exc_type"):
        return True
    for probe in (bootstrap.get("probe_results") or {}).values():
        if isinstance(probe, dict) and probe.get("signal") in ("denied", "exploit", "error"):
            return True
    return False


def analyze_execution(
    code: str,
    *,
    stdout: str = "",
    stderr: str = "",
    exit_code: int = 0,
    timed_out: bool = False,
    error: str = "",
    bootstrap: Optional[Dict[str, Any]] = None,
) -> ExecutionReport:
    probes = detect_code_probes(code)
    probe_results = (bootstrap or {}).get("probe_results") or {}
    if isinstance(probe_results, str):
        try:
            probe_results = json.loads(probe_results)
        except json.JSONDecodeError:
            probe_results = {}

    if bootstrap:
        user_stdout = str(bootstrap.get("user_stdout") if bootstrap.get("user_stdout") is not None else stdout)
        raw_user_stderr = bootstrap.get("user_stderr")
        user_stderr = str(raw_user_stderr) if raw_user_stderr is not None else _strip_bootstrap_lines(stderr)
        exit_code = int(bootstrap.get("exit_code") if bootstrap.get("exit_code") is not None else exit_code)
        errno_val = bootstrap.get("errno")
        if errno_val is not None:
            errno_val = int(errno_val)
        exc_type = str(bootstrap.get("exc_type") or "")
        outcome = _map_bootstrap_outcome(str(bootstrap.get("outcome") or "error"))
        violations = _violation_from_errno_probe(errno_val, exc_type, probes, probe_results)
        if outcome == "allowed" and violations:
            outcome = "denied"
        if (
            suspicious_on_probe_plus_error()
            and probes
            and _bootstrap_has_error_signal(bootstrap)
            and outcome == "allowed"
        ):
            outcome = "suspicious"
            if not violations:
                violations = ("suspicious_probe_signal",)
    else:
        parsed = parse_bootstrap_line(stderr)
        if parsed:
            return analyze_execution(code, bootstrap=parsed)
        user_stdout = stdout
        user_stderr = stderr
        errno_val = None
        exc_type = ""
        violations = detect_output_violations(stdout, stderr)
        if timed_out:
            outcome = "timeout"
            violations = violations + ("execution_timeout",) if "execution_timeout" not in violations else violations
        elif "exploit_succeeded" in violations:
            outcome = "exploit"
        elif violations or "BLOCKED" in f"{stdout}{stderr}":
            outcome = "denied"
        elif exit_code != 0 or error:
            outcome = "error"
        else:
            outcome = "allowed"

    if timed_out:
        outcome = "timeout"
        violations = tuple(dict.fromkeys((*violations, "execution_timeout")))
    elif error and outcome == "allowed":
        outcome = "error"

    vtuple = tuple(dict.fromkeys(violations))

    return ExecutionReport(
        outcome=outcome,
        exit_code=exit_code,
        violation_types=vtuple,
        code_probes=probes,
        code_fingerprint=_fingerprint(code or ""),
        code_lines=max(1, len((code or "").splitlines()) or (1 if (code or "").strip() else 0)),
        stdout_preview=_preview(user_stdout),
        stderr_preview=_preview(user_stderr),
        errno=errno_val if bootstrap else None,
        exc_type=exc_type if bootstrap else "",
    )


def report_from_worker_result(code: str, result: Dict[str, Any]) -> ExecutionReport:
    execution = result.get("execution") or {}
    if execution.get("outcome"):
        violations = execution.get("violations") or []
        if isinstance(violations, str):
            violations = [violations]
        return ExecutionReport(
            outcome=str(execution.get("outcome") or "error"),
            exit_code=int(result.get("exit_code") or execution.get("exit_code") or 0),
            violation_types=tuple(violations),
            code_probes=detect_code_probes(code),
            code_fingerprint=str(execution.get("code_sha") or _fingerprint(code or "")),
            code_lines=max(1, len((code or "").splitlines()) or (1 if (code or "").strip() else 0)),
            stdout_preview=_preview(str(result.get("stdout") or "")),
            stderr_preview=_preview(str(result.get("stderr") or "")),
            errno=execution.get("errno"),
            exc_type=str(execution.get("exc_type") or ""),
        )
    return analyze_execution(
        code,
        stdout=str(result.get("stdout") or ""),
        stderr=str(result.get("stderr") or ""),
        exit_code=int(result.get("exit_code") or 0),
        error=str(result.get("error") or ""),
        timed_out=(result.get("error") == "execution timeout"),
    )


def log_sandbox_execution(
    logger: logging.Logger,
    report: ExecutionReport,
    *,
    tenant_id: str = "",
    worker_url: str = "",
) -> None:
    """Emit one JSON line: short message + structured sandbox object."""
    if not execution_log_enabled():
        return

    if report.outcome == "exploit":
        level = logging.ERROR
    elif report.outcome in ("denied", "suspicious", "timeout", "error"):
        level = logging.WARNING
    else:
        level = logging.INFO

    sandbox: Dict[str, Any] = {
        "outcome": report.outcome,
        "exit_code": report.exit_code,
        "code_sha": report.code_fingerprint,
        "code_lines": report.code_lines,
    }
    if report.violation_label != "none":
        sandbox["violation"] = report.violation_label
    if report.code_probes:
        sandbox["probes"] = list(report.code_probes)
    if report.errno is not None:
        sandbox["errno"] = report.errno
    if report.exc_type:
        sandbox["exc_type"] = report.exc_type
    if report.stdout_preview:
        sandbox["stdout_preview"] = report.stdout_preview
    if report.stderr_preview:
        sandbox["stderr_preview"] = report.stderr_preview
    if worker_url:
        sandbox["worker"] = worker_url

    extra: Dict[str, Any] = {"event": "sandbox_execute", "sandbox": sandbox}
    if tenant_id:
        extra["tenant_id"] = tenant_id
    logger.log(level, "sandbox execute", extra=extra)
