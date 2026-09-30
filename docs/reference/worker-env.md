---
title: Worker Environment
description: Environment variables injected into agent workers by the platform.
type: reference
sidebar_group: Reference
sidebar_order: 22
audience: human
edition: all
---

# Worker Environment Reference

When you deploy a customer agent (e.g., via `zelkor deploy`), the platform automatically injects environment variables into the pod to wire it to the platform gateways.

> **Important:** You must **never** mount real provider API keys (e.g., OpenAI or Anthropic tokens) into the agent worker environment. Provider keys belong in the platform's AI Gateway configuration.

## Injected Variables

The following variables are provided to your agent container:

| Variable | Example Value | Description |
| :--- | :--- | :--- |
| `OPENAI_BASE_URL` | `http://zelkor-platform-ai-gateway:80/v1` | Forces all OpenAI-compatible SDK traffic through the intercept plane. |
| `OPENAI_API_KEY` | `platform-consumer-abc123` | A consumer key used by the AI Gateway for tenant rate-limiting. **Not** the upstream provider key. |
| `MCP_URL` | `http://zelkor-platform-mcp` | The unified MCP gateway endpoint. The agent connects here to discover and call tools. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://zelkor-platform-langfuse:3000` | Points OpenTelemetry traces to the platform Langfuse instance. |
| `LANGFUSE_HOST_HEADER` | `langfuse.example.com` | Used for OTLP routing if required by the ingress topology. |
| `REDIS_CHANNEL_PREFIX` | `aegra:my-agent:run:` | Isolates Server-Sent Events (SSE) and queues on the shared Valkey broker. |

If you are writing raw code (not using Aegra/LangGraph), ensure your LLM clients respect `OPENAI_BASE_URL` and `OPENAI_API_KEY` to inherit platform guardrails and traces.
