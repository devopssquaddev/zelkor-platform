"""Unit tests for the three sandbox checks. No cluster."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

FILES = Path(__file__).resolve().parents[1] / "chart" / "files"
sys.path.insert(0, str(FILES))

from clause_check import HOUSE_MAX_DAYS, check_clause, original_for_clause  # noqa: E402

CONTRACT = (FILES / "contract.txt").read_text(encoding="utf-8")


def test_liability_cap_rejects_unlimited():
    original = original_for_clause(CONTRACT, "liability-cap")
    assert "capped at" in original.lower()
    out = check_clause("liability-cap", original, "The provider accepts unlimited liability.")
    assert out["decision"] == "reject"
    assert out["original"] == original


def test_payment_terms_modifies_net_90():
    original = original_for_clause(CONTRACT, "payment-terms")
    out = check_clause("payment-terms", original, "Fees are due net 90 days after the invoice date.")
    assert out["decision"] == "modify"
    assert out["fallback_days"] == HOUSE_MAX_DAYS
    assert "net" in original.lower()


def test_governing_law_accepts_equal_text():
    original = original_for_clause(CONTRACT, "governing-law")
    out = check_clause("governing-law", original, original)
    assert out["decision"] == "accept"


@pytest.mark.parametrize(
    ("clause_id", "proposed", "decision"),
    [
        ("payment-terms", "Fees are due net 45 days after the invoice date.", "accept"),
        ("liability-cap", "Liability is capped at USD 100,000 per occurrence.", "accept"),
        ("governing-law", "This agreement is governed by New York law.", "reject"),
    ],
)
def test_other_outcomes(clause_id, proposed, decision):
    original = original_for_clause(CONTRACT, clause_id)
    out = check_clause(clause_id, original, proposed)
    assert out["decision"] == decision


def test_module_source_has_no_main_block():
    import inspect
    import clause_check as mod

    assert "if __name__" not in inspect.getsource(mod)
