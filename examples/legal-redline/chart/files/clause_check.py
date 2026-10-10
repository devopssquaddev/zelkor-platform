"""Stdlib clause checks for the legal-redline sandbox call.

The graph sends this module's source plus the contract window and the
proposed sentence. The worker prints one JSON object and exits.
"""
from __future__ import annotations

import json
import re

_CLAUSE_MARK = re.compile(
    r"\[clause_id:\s*([a-z0-9-]+)\]\s*(.*?)(?=\n\[clause_id:|\Z)",
    re.I | re.S,
)
_NET_DAYS = re.compile(r"net\s+(\d+)", re.I)
HOUSE_MAX_DAYS = 45


def original_for_clause(contract_text: str, clause_id: str) -> str:
    wanted = (clause_id or "").strip().lower()
    for match in _CLAUSE_MARK.finditer(contract_text or ""):
        if match.group(1).strip().lower() == wanted:
            return match.group(2).strip()
    return ""


def check_clause(clause_id: str, original: str, proposed: str) -> dict:
    cid = (clause_id or "").strip().lower()
    house = original or ""
    text = proposed or ""
    result = {"original": house, "decision": "reject"}

    if cid == "payment-terms":
        match = _NET_DAYS.search(text)
        if not match:
            return result
        days = int(match.group(1))
        if days <= HOUSE_MAX_DAYS:
            result["decision"] = "accept"
            return result
        result["decision"] = "modify"
        result["fallback_days"] = HOUSE_MAX_DAYS
        return result

    if cid == "liability-cap":
        result["decision"] = "accept" if "capped at" in text.lower() else "reject"
        return result

    if cid == "governing-law":
        result["decision"] = "accept" if house.strip() == text.strip() else "reject"
        return result

    return result
