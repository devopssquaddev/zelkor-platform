"""FinServe records: read a statement window after the pipeline wrote the object."""
from __future__ import annotations

import json
import uuid

import pytest

from finserve_e2e import GRAPH_RECORDS, run_finserve
from tests.helpers.mcp_client import MCPGatewayClient

MARKER = "STATEMENT-OK"


def test_finserve_records_reads_statement_window():
    """The agent reads a key and a text window. The rest of the file is not in the call."""
    writer = MCPGatewayClient("Bank_Alpha")
    key = f"statements/{uuid.uuid4().hex}.txt"
    body = f"Account 1001\n{MARKER}\nEquities 60 percent.\n"
    try:
        names = {tool["name"] for tool in writer.list_tools()}
    except ConnectionError as exc:
        pytest.skip(str(exc))
    if "object__write_text" not in names:
        pytest.skip("object MCP is not enabled")
    writer.call_tool(
        "object__write_text",
        {"key": key, "text": body, "content_type": "text/plain; charset=utf-8"},
    )
    prompt = (
        f"One object__read_text: key {key}, offset 0, length 256. "
        "Quote the text. No other tools."
    )
    result = run_finserve(prompt, tenant_id="Bank_Alpha", graph_id=GRAPH_RECORDS)
    blob = json.dumps(result["raw"], default=str)
    assert MARKER in result["text"] or MARKER in blob


PAGE = 64
PAGE2 = "PAGE2-OK"


def test_finserve_records_paginates_a_long_statement():
    """A statement longer than one window is read in pages. The marker is only on page two."""
    writer = MCPGatewayClient("Bank_Alpha")
    key = f"statements/{uuid.uuid4().hex}.txt"
    body = ("A" * PAGE) + f"\n{PAGE2}\n"
    try:
        names = {tool["name"] for tool in writer.list_tools()}
    except ConnectionError as exc:
        pytest.skip(str(exc))
    if "object__write_text" not in names:
        pytest.skip("object MCP is not enabled")
    writer.call_tool(
        "object__write_text",
        {"key": key, "text": body, "content_type": "text/plain; charset=utf-8"},
    )
    prompt = (
        f"Statement key {key} is longer than one window. "
        f"Call object__read_text with offset 0 and length {PAGE}. "
        f"If eof is false, call object__read_text again with offset {PAGE} and length {PAGE}. "
        f"Quote {PAGE2}. Do not request a length above {PAGE}."
    )
    result = run_finserve(prompt, tenant_id="Bank_Alpha", graph_id=GRAPH_RECORDS, timeout=180.0)
    blob = json.dumps(result["raw"], default=str)
    assert PAGE2 in result["text"] or PAGE2 in blob
    assert blob.count('"object__read_text"') >= 2
    assert '"offset": 0' in blob or '"offset":0' in blob
    assert f'"offset": {PAGE}' in blob or f'"offset":{PAGE}' in blob
