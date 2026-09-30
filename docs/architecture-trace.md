---
title: Run Trace
description: What a single run waterfall looks like in Langfuse.
type: explanation
sidebar_group: Architecture
sidebar_order: 7
audience: human
edition: all
---

# Run Trace

Zelkor provides 100% observability into your agent's behavior. One Agent Protocol run equals exactly one Langfuse trace, automatically joining graph execution, intercepted LLM calls, and tool usage into a single waterfall.

The core advantage: your agent is sandboxed and under observation without relying on the agent code to self-report reliably.

*What one run looks like: The graph, the AI Gateway intercept, and the tool calls all share the same trace context.*
```mermaid
---
config:
  theme: neutral
---
sequenceDiagram
    participant Aegra as Graph Worker
    participant AIGW as AI Gateway
    participant NeMo as NeMo Guardrails
    participant MCP as MCP Gateway

    Note over Aegra,MCP: langfuse.trace.name = graph_id

    Aegra->>Aegra: Start Run (Root Span)
    Aegra->>AIGW: POST /v1/chat/completions (Child Span)
    AIGW->>NeMo: Check prompt
    NeMo-->>AIGW: Rail pass
    AIGW-->>Aegra: Stream chunks
    Aegra->>MCP: tools/call (Child Span)
    MCP-->>Aegra: Tool result
    Aegra->>Aegra: End Run
```

## The Boundary

You deploy the **Agent**. The platform injects the **OpenTelemetry (OTEL)** configuration and propagates the **Trace Context** headers.

Because the AI Gateway intercepts the LLM call, it stamps the Langfuse trace with the exact prompt and completion actually sent to the provider, alongside any guardrail actions taken by NeMo. The graph worker records the overarching logic. 

Langfuse stitches these spans together server-side based on the `sessionId` (the Agent Protocol thread) and the `run_id`, giving you a complete, unbroken waterfall of the run without manually instrumenting your Python code.
