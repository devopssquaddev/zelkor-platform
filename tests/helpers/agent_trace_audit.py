"""Audit a Langfuse trace against internal/plan/requirements_agent_trace.md."""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from tests.helpers.langfuse import (
    blob,
    has_graph_spans,
    has_nemo_spans,
    is_health_probe_trace,
    list_traces,
    observation_io_nonempty,
    trace_detail,
    trace_observations,
    wait_for_traces,
)
from tests.helpers.langgraph_client import aegra_sdk_client


@dataclass
class Check:
    section: str
    requirement: str
    ok: bool
    detail: str = ""


@dataclass
class AuditReport:
    trace_id: str
    checks: list[Check] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.ok for c in self.checks)

    def add(self, section: str, requirement: str, ok: bool, detail: str = "") -> None:
        self.checks.append(Check(section, requirement, ok, detail))

    def print_report(self) -> None:
        print(f"\n=== Agent trace audit: {self.trace_id} ===")
        for c in self.checks:
            mark = "PASS" if c.ok else "FAIL"
            line = f"[{mark}] §{c.section} {c.requirement}"
            if c.detail:
                line += f" — {c.detail}"
            print(line)
        print(f"=== Result: {'COMPLIANT' if self.passed else 'NON-COMPLIANT'} ===\n")


def _obs_names(observations: list[dict]) -> list[str]:
    return [str(o.get("name") or "") for o in observations if isinstance(o, dict)]


def _obs_by_id(observations: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for o in observations:
        if isinstance(o, dict) and o.get("id"):
            out[str(o["id"])] = o
    return out


def _parent_chain(obs: dict, by_id: dict[str, dict]) -> list[str]:
    names: list[str] = []
    cur: dict | None = obs
    seen: set[str] = set()
    while cur and cur.get("id") and str(cur["id"]) not in seen:
        seen.add(str(cur["id"]))
        names.append(str(cur.get("name") or ""))
        pid = cur.get("parentObservationId")
        cur = by_id.get(str(pid)) if pid else None
    return names


def audit_trace(
    trace: dict,
    *,
    expected_graph_id: str,
    expected_user: str,
    expected_session: str,
    capture_content: bool = True,
) -> AuditReport:
    trace_id = str(trace.get("id") or "")
    report = AuditReport(trace_id=trace_id)
    detail = trace_detail(trace_id)
    observations = trace_observations(detail)
    names = _obs_names(observations)
    names_lower = [n.lower() for n in names]
    by_id = _obs_by_id(observations)

    # §1 Identity
    name = str(trace.get("name") or detail.get("name") or "")
    user = str(trace.get("userId") or trace.get("user_id") or detail.get("userId") or "")
    session = str(trace.get("sessionId") or trace.get("session_id") or detail.get("sessionId") or "")
    metadata = trace.get("metadata") or detail.get("metadata") or {}
    run_id = metadata.get("run_id")

    report.add("1", "trace name = graph_id", name == expected_graph_id, f"name={name!r}")
    report.add("1", "userId = tenant", user == expected_user, f"userId={user!r}")
    report.add("1", "sessionId = thread_id", session == expected_session, f"sessionId={session!r}")
    report.add("1", "metadata run_id present", bool(run_id), f"run_id={run_id!r}")

    # §2 Waterfall — graph + NeMo in one trace
    graph_ok = has_graph_spans(observations, detail)
    nemo_ok = has_nemo_spans(observations, detail)
    report.add("2", "graph spans present", graph_ok, f"obs={names[:8]}")
    report.add("2", "NeMo/guardrails spans present", nemo_ok)
    report.add("5", "single trace graph+NeMo (no split)", graph_ok and nemo_ok)

    has_chat = any("chatopenai" in n for n in names_lower)
    has_request = any("chatopenai.request" in n for n in names_lower)
    has_post = any("post" in n and "chat" in n for n in names_lower) or any(
        "chat/completions" in n for n in names_lower
    )
    report.add("2", "ChatOpenAI LLM observation", has_chat, f"matched={[n for n in names if 'chat' in n.lower()][:5]}")
    report.add("2", "ChatOpenAI.request HTTP child", has_request or has_post)

    has_rail = any(
        token in blob(observations)
        for token in ("guardrails", "rail", "content_safety", "guardrails.request")
    )
    report.add("2", "NeMo rail subtree", has_rail)

    # Parent chain: NeMo/post should not be orphan root (has parent when parentObservationId set)
    roots = [o for o in observations if isinstance(o, dict) and not o.get("parentObservationId")]
    orphan_nemo = [
        o.get("name")
        for o in roots
        if any(t in str(o.get("name") or "").lower() for t in ("nemo", "guardrails", "post /v1"))
    ]
    report.add(
        "2",
        "no orphan NeMo/POST roots",
        len(orphan_nemo) == 0,
        f"orphan_roots={orphan_nemo}" if orphan_nemo else "all NeMo spans nested",
    )

    # §3 Observation I/O (captureContent on)
    if capture_content:
        generations = [
            o
            for o in observations
            if isinstance(o, dict)
            and (
                str(o.get("type") or "").upper() == "GENERATION"
                or "generation" in str(o.get("name") or "").lower()
                or "chatopenai" in str(o.get("name") or "").lower()
            )
        ]
        io_ok = any(
            observation_io_nonempty(o.get("input")) and observation_io_nonempty(o.get("output"))
            for o in (generations or observations)
        )
        report.add("3", "GENERATION observation I/O non-empty", io_ok)

        graph_root = next(
            (o for o in observations if str(o.get("name") or "") == expected_graph_id),
            None,
        )
        if graph_root:
            report.add(
                "3",
                "graph root input (user message)",
                observation_io_nonempty(graph_root.get("input")),
            )
            out = graph_root.get("output")
            report.add(
                "3",
                "graph root output (assistant)",
                observation_io_nonempty(out)
                and '"type": "checkpoint"' not in str(out)
                and '"type":"checkpoint"' not in str(out),
            )

    # §4 Audit fields derivable
    report.add("4", "observation count > 1", len(observations) > 1, f"count={len(observations)}")
    has_model = "model" in blob(observations) or any("gpt" in n.lower() for n in names_lower)
    report.add("4", "model id visible in observations", has_model)

    return report


async def run_and_audit(
    *,
    graph_id: str,
    tenant: str = "tenant-a",
    capture_content: bool = True,
) -> AuditReport:
    marker = f"zelkor-audit-{uuid.uuid4().hex[:8]}"
    client = aegra_sdk_client(tenant_id=tenant, graph_id=graph_id)
    thread = await client.threads.create()
    thread_id = thread["thread_id"]
    await client.runs.wait(
        thread_id=thread_id,
        assistant_id=graph_id,
        input={"messages": [{"role": "human", "content": f"Reply with exactly: ok [{marker}]"}]},
    )

    matched = wait_for_traces(
        lambda t: str(t.get("sessionId") or t.get("session_id") or "") == thread_id,
        timeout=60.0,
        name=graph_id,
    )
    if not matched:
        matched = wait_for_traces(
            lambda t: marker in str(t) and str(t.get("name") or "") == graph_id,
            timeout=30.0,
            name=graph_id,
        )
    if not matched:
        raise RuntimeError(f"No Langfuse trace for run graph={graph_id} thread={thread_id}")

    window = [
        t
        for t in list_traces(limit=50, name=graph_id, session_id=thread_id)
        if str(t.get("sessionId") or t.get("session_id") or "") == thread_id
    ]
    if len(window) != 1:
        raise RuntimeError(
            f"Expected exactly one trace for session {thread_id}, got {len(window)}: "
            f"{[t.get('id') for t in window]}"
        )

    report = audit_trace(
        window[0],
        expected_graph_id=graph_id,
        expected_user=tenant,
        expected_session=thread_id,
        capture_content=capture_content,
    )
    report.print_report()

    # Dump observation tree for manual review
    detail = trace_detail(window[0]["id"])
    observations = trace_observations(detail)
    print("Observation names (flat):")
    for o in observations:
        if not isinstance(o, dict):
            continue
        pid = o.get("parentObservationId") or "-"
        print(f"  - {o.get('name')} ({o.get('type')}) parent={pid}")

    return report


def audit_recent_health_probes() -> bool:
    traces = list_traces(limit=30)
    probes = [t for t in traces if is_health_probe_trace(t)]
    ok = len(probes) == 0
    print(f"[{'PASS' if ok else 'FAIL'}] §2 no /v1/health probe traces (found {len(probes)})")
    return ok


async def main() -> int:
    graph_id = os.environ.get("AEGRA_WORKER_GRAPH_ID", "finserve-advisor")
    capture = os.environ.get("NEMO_OTEL_CAPTURE_CONTENT", "1").strip().lower() not in (
        "0",
        "false",
        "off",
    )
    health_ok = audit_recent_health_probes()
    report = await run_and_audit(graph_id=graph_id, capture_content=capture)
    return 0 if report.passed and health_ok else 1


if __name__ == "__main__":
    import asyncio

    sys.exit(asyncio.run(main()))
