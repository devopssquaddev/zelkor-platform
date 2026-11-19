"""CE S-gate manifest and runner (offline): every CE S-id is gated or excluded with a reason."""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "release"))

import fail_closed_matrix as fcm  # noqa: E402
import s_gate  # noqa: E402

CE_IDS = {f"S-{n:02d}" for n in [*range(1, 30), *range(70, 92)]}


def test_manifest_covers_every_ce_id_once():
    m = s_gate.load()
    gated, excluded = set(m["s_ids"]), set(m["excluded"])
    assert not gated & excluded
    assert gated | excluded >= CE_IDS, f"not gated or excluded: {sorted(CE_IDS - gated - excluded)}"
    for sid in gated | excluded:
        assert fcm.SID_RE.fullmatch(sid), sid
    assert all(m["excluded"].values()), "every exclusion needs a reason"


def test_manifest_entries_are_well_formed():
    for sid, spec in s_gate.load()["s_ids"].items():
        assert spec["files"], sid
        assert spec.get("profile", "full") in ("full", "perimeter"), sid
        for f in spec["files"]:
            assert f.endswith(".py") and Path(f).name.startswith("test_"), f


def test_every_matrix_oracle_is_gated():
    """An oracle that the S-gate never runs can never PASS its category."""
    gated = set(s_gate.load()["s_ids"])
    for key, cat in fcm.load_mapping().items():
        for sid in cat["oracle_s_ids"]:
            assert sid in gated, f"{key}: oracle {sid} not in s_gate.yaml"


def _manifest(tmp_path: Path) -> dict:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_s09_a.py").write_text("")
    (tmp_path / "tests" / "test_pol.py").write_text("")
    return {"s_ids": {
        "S-09": {"files": ["tests/test_s09_a.py"]},
        "S-71": {"files": ["tests/test_pol.py"], "env": ["DENY"]},
        "S-72": {"files": ["tests/test_pol.py"]},
        "S-14": {"files": ["tests/test_s14_absent.py"]},
        "S-87": {"profile": "perimeter", "files": ["tests/test_s09_a.py"]},
    }}


def test_missing_file_or_env_is_gap(tmp_path):
    its = s_gate.items(_manifest(tmp_path), "full", {}, root=tmp_path)
    assert [it.s_id for it in its] == ["S-09", "S-71", "S-72", "S-14"]  # perimeter row not in full
    lines = s_gate._plan_lines(its, [])
    assert "GAP S-14: no file tests/test_s14_absent.py" in lines
    assert "GAP S-71: env DENY unset" in lines
    v = s_gate.verdicts(its, [fcm.Case("tests.test_pol", "test_s71_x", "passed")])
    assert v["S-71"][0] == "GAP" and v["S-14"][0] == "GAP"


def test_verdict_by_named_cases_then_by_file(tmp_path):
    its = s_gate.items(_manifest(tmp_path), "full", {"DENY": "t"}, root=tmp_path)
    cases = [fcm.Case("tests.test_s09_a", "test_tcp", "passed"),
             fcm.Case("tests.test_pol", "test_s71_hidden", "passed"),
             fcm.Case("tests.test_pol", "test_s72_rate", "skipped")]
    v = s_gate.verdicts(its, cases)
    assert v["S-09"][0] == "PASS"
    assert v["S-71"][0] == "PASS"  # only its own named case counts
    assert v["S-72"][0] == "GAP"   # skipped is never PASS
    cases.append(fcm.Case("tests.test_s09_a", "test_udp", "failed"))
    assert s_gate.verdicts(its, cases)["S-09"][0] == "FAIL"


def test_plan_on_this_repo_names_the_open_gaps(capsys, monkeypatch):
    for var in yaml.safe_load((ROOT / "scripts/release/s_gate.yaml").read_text())["global_env"]:
        monkeypatch.delenv(var, raising=False)
    assert s_gate.main(["plan"]) == 1
    out = capsys.readouterr().out
    assert "GAP all: global env unset" in out
    assert "tests/test_uat_window_hygiene.py" in out.splitlines()[-1]  # window sweep runs last


def test_report_merges_phases_best_outcome_wins(tmp_path):
    def junit(name, cases, props=""):
        body = "".join(f'<testcase classname="tests.{c}" name="{n}">{"<skipped/>" if o == "skipped" else "<failure/>" if o == "failed" else ""}</testcase>'
                       for c, n, o in cases)
        p = tmp_path / name
        p.write_text(f"<testsuites><testsuite>{props}{body}</testsuite></testsuites>")
        return p
    a = junit("a.xml", [("test_mcp_tool_policy_live", "test_s72_rate", "skipped"),
                        ("test_s09_agent_egress", "test_tcp", "passed")],
              '<properties><property name="zelkor_release" value="9.9.9"/></properties>')
    b = junit("b.xml", [("test_mcp_tool_policy_live", "test_s72_rate", "passed"),
                        ("test_s09_agent_egress", "test_tcp", "failed")])
    out = tmp_path / "m.xml"
    s_gate.merge_junit([a, b], out)
    cases = {c.name: c.outcome for c in fcm.parse_junit(out)}
    assert cases == {"test_s72_rate": "passed", "test_tcp": "failed"}
    assert fcm.parse_properties(out)["zelkor_release"] == "9.9.9"
