---
title: Knowledge Base
description: Index of known issues and troubleshooting guides.
type: reference
sidebar_group: Troubleshooting
sidebar_order: 1
audience: human
edition: all
---

# Knowledge Base

This section contains troubleshooting guides for known issues, edge cases, and common errors encountered when deploying or running the Zelkor platform.

## AI Gateway

* [Vertex `gemini-*` unknown backend](ai-gateway-vertex-unknown-backend.md): Fix AI Gateway 500 errors when Vertex authentication rotation skips the backend.
* [AI Gateway `route_not_found`](ai-gateway-route-not-found.md): Fix 404 on `/v1/chat/completions` after a Helm upgrade cleared the provider key.

## Agent Protocol

* [`POST /runs/wait` 422 `assistant_id`](runs-wait-assistant-id.md): Aegra requires `assistant_id` in the body; `X-Graph-ID` is only routing.
* [JWT rejected (401)](jwt-rejected.md): Token `iss` must match Helm issuer; use a JWKS file when in-cluster JWKS needs a public Host.

## General Troubleshooting

If you encounter an issue not listed here:

1. **Check component logs:** See [Platform Logging](../reference/logging.md) for how to inspect stdout JSON logs for `ERROR` lines.
2. **Check Langfuse traces:** Run traces provide full visibility into LLM calls, MCP tool executions, and NeMo guardrail decisions.
3. **Use the CLI doctor:** Run `zelkor doctor` to verify your environment, credentials, and connection to the platform gateways.
