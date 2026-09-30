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

The Model Context Protocol (MCP) provides a standardized way for agents to interact with external systems. In Zelkor, the **MCP Gateway** aggregates tools from native infrastructure servers and your custom SaaS backends, exposing them securely over a single `MCP_URL` endpoint.

This abstraction ensures that agent code never handles connection strings or SaaS API keys. Instead, the agent requests an action, and the platform injects the required credentials and enforces tenant isolation before executing the tool.

For instructions on adding your own servers, see [Register extra MCP backends](../mcp-extra-backends.md).

## Native Tools

Zelkor ships with several native MCP servers that provide essential infrastructure capabilities out of the box. These tools are strictly governed and automatically enforce tenant boundaries (e.g., injecting row-level security or vector payload filters).

| Backend | Tool | Description |
| :--- | :--- | :--- |
| **Postgres** | `postgres__query` | Executes a SQL query against the platform's Postgres database. Tenant context is injected automatically. |
| **Postgres** | `postgres__list_tables` | Lists available tables in the database, restricted to what the tenant is authorized to see. |
| **Qdrant** | `qdrant__search_documents` | Performs a vector similarity search. The query is automatically wrapped in a `tenant_id` payload filter. |
| **Sandbox** | `sandbox__execute_python` | Executes arbitrary Python code in a secure, ephemeral gVisor container. Used for dynamic data analysis or generating charts. |

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

## Tool Invocation Flow

Agents interact with the MCP Gateway using standard JSON-RPC 2.0 messages. The interaction typically follows two steps:

1. **Discovery (`tools/list`)**: The agent queries the gateway to discover available tools. The gateway aggregates tools from all native and extra backends, applies the appropriate prefix, and returns the unified list.
2. **Execution (`tools/call`)**: The agent invokes a specific tool (e.g., `postgres__query`). The gateway:
   - Identifies the target backend from the prefix.
   - Strips the prefix from the tool name.
   - Enforces the tenant identity (rejecting if the JWT is missing or invalid).
   - Injects the backend secret (database password or SaaS API key).
   - Forwards the request to the target backend and returns the result to the agent.

## `workspace.tools.extraBackends` Schema

You configure custom SaaS MCP servers in `values.yaml` under `workspace.tools.extraBackends`.

| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `name` | string | Yes | The prefix applied to all tools from this backend (e.g., `jira`). Must be lowercase alphanumeric. |
| `url` | string | Yes | The HTTP/SSE endpoint of the backend (e.g., `http://my-jira-mcp:8000/sse`). |
| `forwardHeaders` | list | No | Headers to forward from the agent's request to the backend (e.g., `["Authorization"]`). Essential for passing the Tenant JWT to the backend for identity enforcement. |
| `secretRef` | string | No | The name of a Kubernetes Secret containing the backend's API key. The gateway injects this into the request. |
