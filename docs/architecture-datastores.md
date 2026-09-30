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

To prevent data exfiltration and credential leaks, **agents never receive direct network access or raw connection strings to these databases**. 

Instead, all database access is governed by the Model Context Protocol (MCP) Gateway:
1. The platform runs native MCP servers in front of Postgres and Qdrant.
2. Agents call these stores as tools (e.g., `postgres__query`, `qdrant__search_documents`).
3. The MCP server automatically injects credentials and enforces tenant isolation (Row-Level Security or vector payload filters) before executing the query.

See [MCP Governance](architecture-mcp.md) and [Tenant Isolation](architecture-tenants.md) for deeper details on this boundary.

## Bring Your Own (BYO) Databases

While Zelkor can provision Postgres and Qdrant inside the Kubernetes cluster (using StatefulSets for testing or Operators for production), **customers can bring their own managed databases**.

If you already use Amazon RDS, Google Cloud SQL, or Qdrant Cloud, you can instruct Zelkor to use your external infrastructure instead of provisioning its own.

You configure this in your Helm values during installation:

```yaml
databases:
  mode: external
  
postgresql:
  enabled: false # Disable in-cluster Postgres
  external:
    host: "my-rds-instance.eu-central-1.rds.amazonaws.com"
    port: 5432
    # Authentication provided via external Secret

qdrant:
  enabled: false # Disable in-cluster Qdrant
  external:
    url: "https://my-cluster.aws.cloud.qdrant.io:6333"
    # API key provided via external Secret
```

When using external databases, Zelkor's native MCP servers still act as the governed gateway, ensuring that your agents access your external data securely and with strict tenant isolation.
