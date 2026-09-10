"""Sandbox execution classification for worker/MCP logs (no cluster)."""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "images" / "common"))
sys.path.insert(0, str(ROOT / "mcp"))

from sandbox.execution_report import (  # noqa: E402
    ExecutionReport,
    analyze_execution,
    detect_code_probes,
    log_sandbox_execution,
)
from zelkor_logging import JsonFormatter  # noqa: E402
from tests.test_mcp_sandbox import ADVERSARIAL_DMESG_SCRIPT, ADVERSARIAL_MKNOD_SCRIPT  # noqa: E402


def test_detect_mknod_probe_in_adversarial_script():
    probes = detect_code_probes(ADVERSARIAL_MKNOD_SCRIPT)
    assert "mknod_device" in probes
    assert "host_escape" in probes


def test_mknod_blocked_classified_despite_exit_zero():
    bootstrap = {
        "outcome": "denied",
        "errno": 1,
        "exc_type": "PermissionError",
        "probe_results": {
            "mknod_device": {"ok": False, "signal": "denied", "exc_type": "PermissionError", "errno": 1},
        },
        "user_stdout": "{'mknod_escape': 'BLOCKED: PermissionError'}",
        "user_stderr": "",
        "exit_code": 0,
    }
    report = analyze_execution(ADVERSARIAL_MKNOD_SCRIPT, bootstrap=bootstrap)
    assert report.outcome == "denied"
    assert "permission_denied_mknod" in report.violation_types
    assert report.code_probes
    assert report.code_fingerprint
    assert report.errno == 1


def test_mknod_fallback_regex_still_denied():
    stdout = "{'mknod_escape': 'BLOCKED: PermissionError', 'host_root_visible': False}"
    report = analyze_execution(ADVERSARIAL_MKNOD_SCRIPT, stdout=stdout, exit_code=0)
    assert report.outcome == "denied"
    assert "permission_denied_mknod" in report.violation_types


def test_allowed_benign_print():
    code = "print('sandbox-ok')"
    bootstrap = {
        "outcome": "completed",
        "errno": None,
        "exc_type": "",
        "probe_results": {},
        "user_stdout": "sandbox-ok\n",
        "user_stderr": "",
        "exit_code": 0,
    }
    report = analyze_execution(code, bootstrap=bootstrap)
    assert report.outcome == "allowed"
    assert report.violation_types == ()


def test_exploit_succeeded_is_exploit_outcome():
    bootstrap = {
        "outcome": "exploit",
        "errno": None,
        "exc_type": "",
        "probe_results": {"mknod_device": {"ok": False, "signal": "exploit"}},
        "user_stdout": "{'mknod_escape': 'EXPLOIT_SUCCEEDED'}",
        "user_stderr": "",
        "exit_code": 0,
    }
    report = analyze_execution(ADVERSARIAL_MKNOD_SCRIPT, bootstrap=bootstrap)
    assert report.outcome == "exploit"
    assert "exploit_mknod_device" in report.violation_types or "exploit_succeeded" in report.violation_types


def test_suspicious_when_probe_plus_error_but_user_caught(monkeypatch):
    monkeypatch.setenv("SANDBOX_SUSPICIOUS_ON_PROBE_PLUS_ERROR", "true")
    bootstrap = {
        "outcome": "completed",
        "errno": 1,
        "exc_type": "PermissionError",
        "probe_results": {
            "mknod_device": {"ok": False, "signal": "denied", "exc_type": "PermissionError", "errno": 1},
        },
        "user_stdout": "all good",
        "user_stderr": "",
        "exit_code": 0,
    }
    report = analyze_execution(ADVERSARIAL_MKNOD_SCRIPT, bootstrap=bootstrap)
    assert report.outcome in ("denied", "suspicious")


def test_log_sandbox_execution_structured_json(monkeypatch):
    monkeypatch.setenv("SANDBOX_EXECUTION_LOG_ENABLED", "true")
    monkeypatch.setenv("SANDBOX_INCLUDE_STDOUT_PREVIEW", "true")
    report = ExecutionReport(
        outcome="denied",
        exit_code=0,
        violation_types=("permission_denied_mknod",),
        code_probes=("mknod_device",),
        code_fingerprint="644f169bde8a",
        code_lines=12,
        stdout_preview="{'mknod_escape': 'BLOCKED: PermissionError'}",
        stderr_preview="",
        errno=1,
        exc_type="PermissionError",
    )
    record = logging.LogRecord("zelkor-sandbox-worker", logging.WARNING, "", 0, "", (), None)
    record.component = "zelkor-sandbox-worker"

    class _CaptureHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            self.last = record

    handler = _CaptureHandler()
    logger = logging.getLogger("test-sandbox-log")
    logger.handlers = [handler]
    logger.setLevel(logging.DEBUG)
    log_sandbox_execution(logger, report, tenant_id="tenant_a")
    payload = json.loads(JsonFormatter().format(handler.last))
    assert payload["message"] == "sandbox execute"
    assert payload["event"] == "sandbox_execute"
    assert payload["tenant_id"] == "tenant_a"
    assert payload["sandbox"]["outcome"] == "denied"
    assert payload["sandbox"]["violation"] == "permission_denied_mknod"
    assert "ZELKOR_SANDBOX_RESULT" not in json.dumps(payload)


def test_stderr_preview_strips_bootstrap_envelope():
    stderr = (
        'ZELKOR_SANDBOX_RESULT {"outcome":"denied","errno":1}\n'
        "user traceback line"
    )
    report = analyze_execution("print(1)", stderr=stderr, exit_code=0)
    assert "ZELKOR_SANDBOX_RESULT" not in report.stderr_preview


def test_dmesg_script_probes_and_isolation_signal():
    probes = detect_code_probes(ADVERSARIAL_DMESG_SCRIPT)
    assert "dmesg_probe" in probes
    assert "reboot_syscall" in probes or "ctypes_privileged" in probes
    stdout = "{'dmesg_isolated': True, 'reboot_syscall': 'RETURNED_-1'}"
    report = analyze_execution(ADVERSARIAL_DMESG_SCRIPT, stdout=stdout, exit_code=0)
    assert report.outcome == "allowed"
    assert report.violation_types == ()
    leaked = analyze_execution(
        ADVERSARIAL_DMESG_SCRIPT,
        stdout="{'dmesg_isolated': False, 'reboot_syscall': 'RETURNED_0'}",
        exit_code=0,
    )
    assert "dmesg_not_isolated" in leaked.violation_types
    assert leaked.outcome == "denied"
