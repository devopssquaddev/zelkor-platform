"""Fixed-order legal-redline graph. Not create_agent. Not a Deep Agent.

object__read_text → sandbox__execute_python → qdrant__search_documents →
one gateway model call for the comment. The graph copies decision from
the sandbox JSON.
"""
from __future__ import annotations

import inspect
import json
import logging
import os
from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

import clause_check

logger = logging.getLogger("zelkor-legal-redline")

COLLECTION = os.getenv("QDRANT_COLLECTION", "legal_redline_playbook")
DEFAULT_KEY = "contracts/msa.txt"
MODEL = os.getenv("DEFAULT_LLM_MODEL", "")

class ReviewState(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    clause_id: str
    object_key: str
    proposed: str
    counterparty: str
    record: bool
    contract_text: str
    sandbox: dict
    playbook: list
    suggestion: dict


def _json_objects(raw: str) -> list[Any]:
    text = (raw or "").strip()
    if text.startswith("Error:"):
        raise RuntimeError(text)
    out: list[Any] = []
    decoder = json.JSONDecoder()
    idx = 0
    while idx < len(text):
        while idx < len(text) and text[idx].isspace():
            idx += 1
        if idx >= len(text):
            break
        start = text.find("{", idx)
        if start < 0:
            break
        try:
            obj, end = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            idx = start + 1
            continue
        out.append(obj)
        idx = end
    return out


def _parse_json(raw: str) -> Any:
    objs = _json_objects(raw)
    if not objs:
        return {}
    return objs[-1]


def _sandbox_from_tool(raw: str) -> dict:
    for parsed in reversed(_json_objects(raw)):
        if not isinstance(parsed, dict):
            continue
        if parsed.get("decision"):
            return parsed
        if parsed.get("stdout"):
            for inner in reversed(_json_objects(str(parsed.get("stdout") or ""))):
                if isinstance(inner, dict) and inner.get("decision"):
                    return inner
    raise RuntimeError("sandbox did not print a decision")


def _playbook_docs(raw: str) -> list[dict]:
    parsed = _parse_json(raw)
    if not isinstance(parsed, dict):
        return []
    docs = parsed.get("documents") or parsed.get("points") or []
    out: list[dict] = []
    for item in docs:
        if not isinstance(item, dict):
            continue
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else item
        out.append(payload)
    return out


def _rule_ids(docs: list[dict], clause_id: str) -> list[str]:
    wanted = (clause_id or "").strip().lower()
    matched: list[str] = []
    fallback: list[str] = []
    for doc in docs:
        rid = str(doc.get("rule_id") or "").strip()
        if not rid:
            continue
        fallback.append(rid)
        if str(doc.get("clause_id") or "").strip().lower() == wanted:
            matched.append(rid)
    return matched or fallback


def _last_human(state: ReviewState) -> str:
    for msg in reversed(state.get("messages") or []):
        role = ""
        content = ""
        if isinstance(msg, dict):
            role = str(msg.get("role") or msg.get("type") or "").lower()
            content = str(msg.get("content") or "")
        else:
            role = str(getattr(msg, "type", "") or getattr(msg, "role", "")).lower()
            content = str(getattr(msg, "content", "") or "")
        if role in ("human", "user"):
            return content
    return ""


def _sandbox_code(clause_id: str, contract_text: str, proposed: str) -> str:
    source = inspect.getsource(clause_check).split('if __name__')[0]
    return (
        source
        + "\n"
        + "contract = "
        + repr(contract_text)
        + "\n"
        + "proposed = "
        + repr(proposed)
        + "\n"
        + "clause_id = "
        + repr(clause_id)
        + "\n"
        + "original = original_for_clause(contract, clause_id)\n"
        + "print(json.dumps(check_clause(clause_id, original, proposed)))\n"
    )


def _model() -> ChatOpenAI:
    key = os.getenv("OPENAI_API_KEY") or "not-required"
    return ChatOpenAI(model=MODEL, temperature=0, api_key=key)


def _route(state: ReviewState) -> Literal["record_decision", "followup", "read_object"]:
    if state.get("record") and state.get("suggestion"):
        return "record_decision"
    if state.get("suggestion"):
        return "followup"
    return "read_object"


async def read_object(state: ReviewState) -> dict:
    from mcp_inject import call_tool

    key = (state.get("object_key") or DEFAULT_KEY).strip() or DEFAULT_KEY
    logger.info("object read", extra={"event": "tools_call", "graph_id": "legal-redline"})
    raw = await call_tool("object__read_text", {"key": key, "offset": 0, "length": 65536})
    parsed = _parse_json(raw)
    text = ""
    if isinstance(parsed, dict):
        text = str(parsed.get("text") or "")
    if not text:
        raise RuntimeError("object__read_text returned no contract text")
    return {"contract_text": text, "object_key": key}


async def sandbox_check(state: ReviewState) -> dict:
    from mcp_inject import call_tool

    clause_id = (state.get("clause_id") or "").strip()
    proposed = state.get("proposed") or ""
    code = _sandbox_code(clause_id, state.get("contract_text") or "", proposed)
    logger.info("sandbox check", extra={"event": "tools_call", "graph_id": "legal-redline"})
    raw = await call_tool("sandbox__execute_python", {"code": code, "timeout": 15})
    sandbox = _sandbox_from_tool(raw)
    return {"sandbox": sandbox}


async def search_playbook(state: ReviewState) -> dict:
    from mcp_inject import call_tool

    clause_id = (state.get("clause_id") or "").strip()
    query = f"{clause_id} {(state.get('proposed') or '')}".strip()
    logger.info("playbook search", extra={"event": "tools_call", "graph_id": "legal-redline"})
    raw = await call_tool(
        "qdrant__search_documents",
        {"query": query, "collection": COLLECTION, "limit": 8},
    )
    return {"playbook": _playbook_docs(raw)}


async def write_comment(state: ReviewState) -> dict:
    sandbox = state.get("sandbox") or {}
    decision = str(sandbox.get("decision") or "reject")
    docs = state.get("playbook") or []
    rule_ids = _rule_ids(docs, state.get("clause_id") or "")
    playbook_text = json.dumps(docs, default=str)
    sandbox_text = json.dumps(sandbox, default=str)
    system = (
        "You write a short first-person redline comment for a lawyer. "
        "Do not change the house-position decision already set. "
        "Do not mention sandbox, tools, models, or infrastructure. "
        "Do not add a chatty preamble. "
        "Return JSON only with comment, risk (low|medium|high), "
        "matched_rule_ids (from the playbook), and replacement only when "
        "decision is modify. replacement must use fallback_days when present."
    )
    human = (
        f"decision={decision}\n"
        f"house_check={sandbox_text}\n"
        f"playbook={playbook_text}\n"
        f"clause_id={state.get('clause_id') or ''}\n"
        f"counterparty={state.get('counterparty') or ''}\n"
        f"Write the comment. matched_rule_ids must be a subset of {rule_ids}."
    )
    logger.info("comment model", extra={"event": "model_call", "graph_id": "legal-redline"})
    resp = await _model().ainvoke(
        [SystemMessage(content=system), HumanMessage(content=human)]
    )
    parsed = _parse_json(str(getattr(resp, "content", "") or ""))
    if not isinstance(parsed, dict):
        parsed = {}
    comment = str(parsed.get("comment") or "House position stands.").strip()
    risk = str(parsed.get("risk") or "medium").strip().lower()
    if risk not in ("low", "medium", "high"):
        risk = "medium"
    ids = parsed.get("matched_rule_ids")
    if not isinstance(ids, list) or not ids:
        ids = rule_ids
    ids = [str(x) for x in ids if str(x) in set(rule_ids) or not rule_ids]
    if not ids:
        ids = rule_ids
    suggestion: dict[str, Any] = {
        "decision": decision,
        "comment": comment,
        "risk": risk,
        "matched_rule_ids": ids,
    }
    if decision == "modify":
        days = sandbox.get("fallback_days") or clause_check.HOUSE_MAX_DAYS
        replacement = str(parsed.get("replacement") or "").strip()
        if f"net {days}" not in replacement.lower():
            replacement = f"Fees are due net {days} days after the invoice date."
        suggestion["replacement"] = replacement
    return {
        "suggestion": suggestion,
        "messages": [AIMessage(content=json.dumps(suggestion))],
    }


async def followup(state: ReviewState) -> dict:
    suggestion = state.get("suggestion") or {}
    sandbox = state.get("sandbox") or {}
    question = _last_human(state)
    body = {
        "decision": suggestion.get("decision") or sandbox.get("decision"),
        "comment": suggestion.get("comment") or "",
        "why": (
            "The house playbook already set this recommendation. "
            f"We recommend {sandbox.get('decision') or suggestion.get('decision')}. "
            f"The house wording is: {sandbox.get('original') or ''}."
        ),
        "question": question,
    }
    logger.info("followup", extra={"event": "followup", "graph_id": "legal-redline"})
    return {"messages": [AIMessage(content=json.dumps(body))]}


async def record_decision(state: ReviewState) -> dict:
    from mcp_inject import call_tool

    suggestion = state.get("suggestion") or {}
    content = json.dumps(
        {
            "clause_id": state.get("clause_id") or "",
            "decision": suggestion.get("decision"),
            "comment": suggestion.get("comment") or "",
        },
        default=str,
    )
    logger.info("record playbook", extra={"event": "tools_call", "graph_id": "legal-redline"})
    await call_tool(
        "qdrant__upsert_document",
        {
            "collection": COLLECTION,
            "content": content,
            "metadata": {
                "clause_id": state.get("clause_id") or "",
                "rule_id": f"recorded-{(state.get('clause_id') or 'clause')}",
            },
        },
    )
    return {"messages": [AIMessage(content=json.dumps({"recorded": True, **suggestion}))]}


_builder = StateGraph(ReviewState)
_builder.add_node("read_object", read_object)
_builder.add_node("sandbox_check", sandbox_check)
_builder.add_node("search_playbook", search_playbook)
_builder.add_node("write_comment", write_comment)
_builder.add_node("followup", followup)
_builder.add_node("record_decision", record_decision)
_builder.add_conditional_edges(
    START,
    _route,
    {
        "record_decision": "record_decision",
        "followup": "followup",
        "read_object": "read_object",
    },
)
_builder.add_edge("read_object", "sandbox_check")
_builder.add_edge("sandbox_check", "search_playbook")
_builder.add_edge("search_playbook", "write_comment")
_builder.add_edge("write_comment", END)
_builder.add_edge("followup", END)
_builder.add_edge("record_decision", END)
graph = _builder.compile()
