---
title: Agent Datastores
description: Overview of the stateful infrastructure (Postgres and Qdrant) used by agents and BYO options.
type: explanation
sidebar_group: Architecture
sidebar_order: 40
audience: human
edition: all
---

# Agent Datastores

AI agents require stateful infrastructure for persistent memory, relational data, and vector embeddings (RAG). Zelkor provides this infrastructure out of the box while maintaining strict sandbox and tenant isolation.

## Core Infrastructure

By default, the platform provisions and manages two primary datastores for your agents:

- **Postgres:** Used for relational data, persistent agent memory (e.g., LangGraph thread state), and structured business data.
- **Qdrant:** A high-performance vector database used for storing embeddings and performing similarity searches (RAG workloads).

## How Agents Access Data

Connection strings stay on the MCP servers. The agent calls tools; it does not receive the database password.

Direct network access from the agent pod is blocked only when NetworkPolicies are on. The [production install](production.md) turns them on. The chart default and the evaluation install leave `security.networkPolicies.enabled` false, so that deny is not in effect until you enable it.

Database calls go through the MCP gateway:
1. The platform runs native MCP servers in front of Postgres and Qdrant.
2. Agents call these stores as tools (`postgres__query`, `qdrant__search_documents`).
3. The MCP server holds the credentials. Postgres sets `app.current_tenant` for the transaction and does not rewrite the SQL. Qdrant filters on payload `tenant_id`.

See [MCP Governance](architecture-mcp.md) and [Tenant Isolation](architecture-tenants.md) for deeper details on this boundary.

## Bring Your Own (BYO) Databases

Zelkor can run Postgres and Qdrant in the cluster (StatefulSets for evaluation, operators for production). Set `databases.mode: external` to use your own Postgres, ClickHouse, and Valkey instead. That mode does not start the in-cluster copies.

```yaml
databases:
  mode: external
  postgresql:
    external:
      host: "my-rds-instance.example.com"
      port: 5432
  clickhouse:
    external:
      host: "clickhouse.example.com"
  valkey:
    external:
      host: "valkey.example.com"

mcp:
  qdrantMCP:
    url: "http://qdrant.example.com:6333"
```

There is no Qdrant block under `databases`. Point `mcp.qdrantMCP.url` at the Qdrant you already run. Postgres and ClickHouse passwords are `postgresql.auth.password` and `clickhouse.auth.password`, or `databases.postgresql.external.password` and `databases.clickhouse.external.password` when `mode` is `external`. Valkey uses `valkey.auth.password`. The native MCP servers still sit in front of those hosts. See the [Helm values reference](reference/helm-values.md).
