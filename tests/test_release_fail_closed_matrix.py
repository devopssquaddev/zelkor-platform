"""CE-19e: fail-closed negative matrix generated from the S-gate JUnit XML (offline)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "release"))

import fail_closed_matrix as fcm  # noqa: E402

MAPPING = ROOT / "scripts" / "release" / "fail_closed_categories.yaml"
SPEC_CATEGORIES = {"auth", "guardrails", "egress", "egress-dns", "admin-plane", "provider-keys", "component-down"}


def _junit(tmp_path: Path, cases: list[tuple[str, str, str]]) -> Path:
    """cases: (classname, name, outcome) with outcome passed|failed|error|skipped."""
    body = []
    for cls, name, outcome in cases:
        inner = {"failed": '<failure message="boom">trace with https://lab.internal</failure>',
                 "error": '<error message="setup">x</error>',
                 "skipped": '<skipped message="NP off" />'}.get(outcome, "")
        body.append(f'<testcase classname="{cls}" name="{name}" time="0.1">{inner}</testcase>')
    xml = ('<?xml version="1.0"?><testsuites><testsuite name="pytest" tests="%d">%s</testsuite></testsuites>'
           % (len(cases), "".join(body)))
    path = tmp_path / "s-gate.junit.xml"
    path.write_text(xml)
    return path


def test_mapping_has_the_spec_categories_and_valid_ids():
    data = yaml.safe_load(MAPPING.read_text())
    assert set(data["categories"]) == SPEC_CATEGORIES
    for key, cat in data["categories"].items():
        assert cat["title"], key
        for sid in cat.get("s_ids", []):
            assert fcm.SID_RE.fullmatch(sid), sid
        for f in cat.get("files", []):
            assert (ROOT / "tests" / f"{f}.py").is_file() or "/" in f, f"{key}: tests/{f}.py missing"


def test_s_ids_from_file_and_test_names():
    assert fcm.s_ids("tests.test_s09_agent_egress", "test_x") == {"S-09"}
    assert fcm.s_ids("tests.test_ingress", "test_s11_ingress_inventory") == {"S-11"}
    assert fcm.s_ids("tests.test_tenant_auth", "test_rejects_unsigned") == set()
    assert fcm.s_ids("tests.test_s75_runtime_egress", "test_s83_extra") == {"S-75", "S-83"}


def test_categories_pass_fail_and_gap(tmp_path):
    junit = _junit(tmp_path, [
        ("tests.test_s09_agent_egress", "test_tcp_refused", "passed"),
        ("tests.test_s83_gateway_bypass", "test_no_key_401", "failed"),
        ("tests.test_s16_agent_env", "test_no_provider_key", "skipped"),
        ("tests.test_s04_prompt_tenant", "test_forged_tenant", "passed"),
    ])
    report = fcm.build(fcm.load_mapping(MAPPING), fcm.parse_junit(junit))
    status = {c.key: c.status for c in report.categories}
    assert status["egress"] == "PASS"
    assert status["guardrails"] == "FAIL"
    assert status["provider-keys"] == "GAP"  # only skips: SKIP is never PASS
    assert status["egress-dns"] == "GAP"
    assert status["component-down"] == "GAP"
    assert [o.s_ids for o in report.other] == [["S-04"]]


def test_s90_turns_egress_dns_pass(tmp_path):
    junit = _junit(tmp_path, [("tests.test_s90_dns_egress_live", "test_s90_locked_agents_cannot_resolve_or_reach_dns",
                               "passed")])
    report = fcm.build(fcm.load_mapping(MAPPING), fcm.parse_junit(junit))
    assert {c.key: c.status for c in report.categories}["egress-dns"] == "PASS"


def test_error_counts_as_failure(tmp_path):
    junit = _junit(tmp_path, [("tests.test_s09_agent_egress", "a", "passed"),
                              ("tests.test_s09_agent_egress", "b", "error")])
    report = fcm.build(fcm.load_mapping(MAPPING), fcm.parse_junit(junit))
    assert next(c for c in report.categories if c.key == "egress").status == "FAIL"


def test_markdown_lists_every_category_and_no_failure_text(tmp_path):
    junit = _junit(tmp_path, [("tests.test_s83_gateway_bypass", "test_no_key_401", "failed")])
    md = fcm.render(fcm.build(fcm.load_mapping(MAPPING), fcm.parse_junit(junit)), tag="v9.9.9-ce")
    for key in SPEC_CATEGORIES:
        assert yaml.safe_load(MAPPING.read_text())["categories"][key]["title"] in md
    assert "| FAIL |" in md and "| GAP |" in md
    assert "lab.internal" not in md and "boom" not in md
    assert "v9.9.9-ce" in md


def test_missing_evidence_is_visible_not_skipped(tmp_path, capsys):
    out = tmp_path / "m.md"
    rc = fcm.main(["--tag", "v9.9.9-ce", "--junit", str(tmp_path / "absent.xml"), "--out", str(out)])
    md = out.read_text()
    assert rc == 0
    assert "No S-gate evidence" in md
    assert "| PASS |" not in md
    assert md.count("| GAP |") == len(SPEC_CATEGORIES)
    assert "::warning" in capsys.readouterr().out


def test_require_evidence_fails_when_missing(tmp_path):
    rc = fcm.main(["--tag", "v9.9.9-ce", "--junit", str(tmp_path / "absent.xml"),
                   "--out", str(tmp_path / "m.md"), "--require-evidence"])
    assert rc == 1


def test_cli_exit_reflects_failures(tmp_path):
    junit = _junit(tmp_path, [("tests.test_s83_gateway_bypass", "t", "failed")])
    r = subprocess.run([sys.executable, str(ROOT / "scripts/release/fail_closed_matrix.py"), "--tag", "v1.0.0-ce",
                        "--junit", str(junit), "--out", str(tmp_path / "m.md")], capture_output=True, text=True)
    assert r.returncode == 0  # the report is published either way; the S-gate itself blocks the tag
    assert "FAIL" in (tmp_path / "m.md").read_text()


@pytest.mark.parametrize("bad", ["<testsuites><testsuite>", "not xml"])
def test_malformed_junit_is_an_error(tmp_path, bad):
    p = tmp_path / "j.xml"
    p.write_text(bad)
    with pytest.raises(ValueError):
        fcm.parse_junit(p)
