---
title: MCP Tools Reference
description: Tool prefixes, list mechanics, and extraBackends fields.
type: reference
sidebar_group: Reference
sidebar_order: 23
audience: human
edition: all
---

# MCP Tools Reference

The Zelkor MCP Gateway aggregates tools from native servers and your custom SaaS backends. It exposes them to agents over a single `MCP_URL`.

For instructions on adding your own servers, see [Register extra MCP backends](../mcp-extra-backends.md).

## Tool Prefixes

To prevent naming collisions, the gateway prefixes tool names based on the server that provides them. When an agent calls `tools/list`, it sees the prefixed names.

| Server / Backend | Original Tool Name | Agent Sees |
| :--- | :--- | :--- |
| **Postgres (Native)** | `query` | `postgres__query` |
| **Postgres (Native)** | `list_tables` | `postgres__list_tables` |
| **Qdrant (Native)** | `search_documents` | `qdrant__search_documents` |
| **Sandbox (Native)** | `execute_python` | `sandbox__execute_python` |
| **Extra (e.g., `jira`)** | `create_issue` | `jira__create_issue` |

*Note: Double underscores (`__`) separate the server prefix from the tool name.*

## `workspace.tools.extraBackends` Schema

You configure custom SaaS MCP servers in `values.yaml` under `workspace.tools.extraBackends`.

| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `name` | string | Yes | The prefix applied to all tools from this backend (e.g., `jira`). Must be lowercase alphanumeric. |
| `url` | string | Yes | The HTTP/SSE endpoint of the backend (e.g., `http://my-jira-mcp:8000/sse`). |
| `forwardHeaders` | list | No | Headers to forward from the agent's request to the backend (e.g., `["Authorization"]`). Essential for passing the Tenant JWT to the backend for identity enforcement. |
| `secretRef` | string | No | The name of a Kubernetes Secret containing the backend's API key. The gateway injects this into the request. |
