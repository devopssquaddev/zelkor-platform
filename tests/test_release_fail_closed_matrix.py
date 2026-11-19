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
SPEC_CATEGORIES = {"auth", "guardrails", "egress", "egress-dns", "admin-plane", "provider-keys", "component-down",
                   "tenant-data", "sandbox", "tool-and-rate-limits"}


def _junit(tmp_path: Path, cases: list[tuple[str, str, str]], props: dict | None = None) -> Path:
    """cases: (classname, name, outcome) with outcome passed|failed|error|skipped."""
    body = []
    for cls, name, outcome in cases:
        inner = {"failed": '<failure message="boom">trace with https://lab.internal</failure>',
                 "error": '<error message="setup">x</error>',
                 "skipped": '<skipped message="NP off" />'}.get(outcome, "")
        body.append(f'<testcase classname="{cls}" name="{name}" time="0.1">{inner}</testcase>')
    properties = "".join(f'<property name="{k}" value="{v}" />' for k, v in (props or {}).items())
    properties = f"<properties>{properties}</properties>" if properties else ""
    xml = ('<?xml version="1.0"?><testsuites><testsuite name="pytest" tests="%d">%s%s</testsuite></testsuites>'
           % (len(cases), properties, "".join(body)))
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
        assert cat.get("oracle_s_ids"), f"{key}: no oracle S-id (a category without one can never PASS)"
        assert set(cat["oracle_s_ids"]) <= set(cat["s_ids"]), f"{key}: oracle not in s_ids"
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
        ("tests.test_s75_runtime_egress", "test_env", "passed"),
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
    assert status["tenant-data"] == "GAP"  # S-04 passed, other oracles absent
    assert report.other == []


def test_s90_turns_egress_dns_pass(tmp_path):
    junit = _junit(tmp_path, [("tests.test_s90_dns_egress_live", "test_s90_locked_agents_cannot_resolve_or_reach_dns",
                               "passed")])
    report = fcm.build(fcm.load_mapping(MAPPING), fcm.parse_junit(junit))
    assert {c.key: c.status for c in report.categories}["egress-dns"] == "PASS"


def test_error_counts_as_failure(tmp_path):
    junit = _junit(tmp_path, [("tests.test_s09_agent_egress", "a", "passed"),
                              ("tests.test_s75_runtime_egress", "a", "passed"),
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


def test_non_oracle_pass_never_earns_pass(tmp_path):
    """Coverage audit G3: config-only or positive tests in a category cannot make it PASS."""
    junit = _junit(tmp_path, [("tests.test_mcp_postgres_fail_closed", "test_x", "passed"),
                              ("tests.test_uat_runtime_resilience", "test_y", "passed"),
                              ("tests.test_tenant_auth", "test_rs256_ok", "passed")])
    report = fcm.build(fcm.load_mapping(MAPPING), fcm.parse_junit(junit))
    row = {c.key: c for c in report.categories}
    assert row["component-down"].status == "GAP"
    assert row["component-down"].missing == ["S-03", "S-25"]
    assert row["auth"].status == "GAP"


def test_skipped_oracle_is_gap_even_when_another_case_passed(tmp_path):
    junit = _junit(tmp_path, [("tests.test_s03_nemo_down", "test_chat_5xx", "passed"),
                              ("tests.test_s25_gvisor_live", "test_pending", "passed"),
                              ("tests.test_s25_gvisor_live", "test_no_runc", "skipped")])
    row = {c.key: c for c in fcm.build(fcm.load_mapping(MAPPING), fcm.parse_junit(junit)).categories}
    assert row["component-down"].status == "GAP"
    assert row["component-down"].missing == ["S-25"]


def test_all_oracles_pass(tmp_path):
    junit = _junit(tmp_path, [("tests.test_s03_nemo_down", "a", "passed"),
                              ("tests.test_s25_gvisor_live", "b", "passed")])
    row = {c.key: c for c in fcm.build(fcm.load_mapping(MAPPING), fcm.parse_junit(junit)).categories}
    assert row["component-down"].status == "PASS"


def test_class_based_testcase_maps_by_file_stem():
    assert fcm.Case("tests.test_ingress.TestRoutes", "test_a", "passed").module == "test_ingress"
    assert fcm.Case("tests.test_ingress", "test_a", "passed").module == "test_ingress"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    (r / "charts").mkdir(parents=True)
    (r / "charts" / "c.yaml").write_text("a: 1\n")
    (r / "docs").mkdir()
    _git(r.parent, "init", "-q", str(r))
    _git(r, "-c", "user.email=t@t", "-c", "user.name=t", "add", ".")
    _git(r, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "base")
    return r


def _commit(repo: Path, path: str, text: str, tag: str) -> str:
    (repo / path).write_text(text)
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qam", path)
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "tag", "-a", tag, "-m", tag)
    return _git(repo, "rev-parse", "HEAD")


def test_evidence_must_carry_run_properties(repo):
    assert "zelkor_release" in fcm.evidence_problems({}, "v1.0.0-ce", repo)[0]


def test_evidence_for_the_tag_is_bound(repo):
    sha = _git(repo, "rev-parse", "HEAD")
    props = {"zelkor_release": "1.0.0", "zelkor_git_sha": sha, "zelkor_run_id": "r1"}
    assert fcm.evidence_problems(props, "v1.0.0-ce", repo) == []


def test_carry_over_allowed_only_when_product_paths_unchanged(repo):
    sha = _git(repo, "rev-parse", "HEAD")
    props = {"zelkor_release": "1.0.0", "zelkor_git_sha": sha, "zelkor_run_id": "r1"}
    (repo / "docs" / "a.md").write_text("x")
    _git(repo, "add", "docs/a.md")
    _commit(repo, "docs/a.md", "docs only", "v1.0.1-ce")
    assert fcm.evidence_problems(props, "v1.0.1-ce", repo) == []
    _commit(repo, "charts/c.yaml", "a: 2\n", "v1.0.2-ce")
    assert "product paths changed" in fcm.evidence_problems(props, "v1.0.2-ce", repo)[0]


def test_require_evidence_fails_on_unbound_or_failed_run(tmp_path, repo):
    sha = _git(repo, "rev-parse", "HEAD")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "tag", "-a", "v1.0.0-ce", "-m", "t")
    good = {"zelkor_release": "1.0.0", "zelkor_git_sha": sha, "zelkor_run_id": "r1"}
    args = ["--tag", "v1.0.0-ce", "--out", str(tmp_path / "m.md"), "--require-evidence", "--repo", str(repo)]
    unbound = _junit(tmp_path, [("tests.test_s09_agent_egress", "a", "passed")])
    assert fcm.main([*args, "--junit", str(unbound)]) == 1
    bound = _junit(tmp_path, [("tests.test_s09_agent_egress", "a", "passed")], good)
    assert fcm.main([*args, "--junit", str(bound)]) == 0
    assert "Tested release `1.0.0`" in (tmp_path / "m.md").read_text()
    assert fcm.main([*args, "--junit", str(bound), "--strict"]) == 1  # GAPs remain
    failed = _junit(tmp_path, [("tests.test_s09_agent_egress", "a", "failed")], good)
    assert fcm.main([*args, "--junit", str(failed)]) == 1


def test_cases_without_an_s_id_in_their_name_take_it_from_the_s_gate_file_map(tmp_path):
    """UAT-27 proves S-80, test_mcp_tenant proves S-04: the S-gate manifest names the file."""
    by_file = fcm.file_s_ids()
    assert by_file["test_uat27_a2a_northbound"] == {"S-80"}
    junit = _junit(tmp_path, [("tests.test_uat27_a2a_northbound", "test_uat27_card_is_public_rpc_needs_a_jwt", "passed"),
                              ("tests.test_mcp_tool_policy_live", "test_s71_denied_tool_hidden", "passed")])
    report = fcm.build(fcm.load_mapping(MAPPING), fcm.parse_junit(junit), by_file)
    auth = next(c for c in report.categories if c.key == "auth")
    assert "S-80" in auth.oracle_passed
    tools = next(c for c in report.categories if c.key == "tool-and-rate-limits")
    assert tools.oracle_passed == {"S-71"}  # a named case keeps its own id, not every id of its file
