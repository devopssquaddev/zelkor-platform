---
title: Network Boundaries
description: Who may talk to whom inside the cluster and how NetworkPolicies isolate the agent.
type: explanation
sidebar_group: Architecture
sidebar_order: 4
audience: human
edition: all
---

# Network Boundaries

Zelkor enforces zero-trust boundaries around your agent workload. It uses strict Kubernetes NetworkPolicies to ensure the agent cannot bypass governance.

The core advantage: your agent is sandboxed and cannot reach unauthorized data or dial out to the internet directly.

*Who may talk to whom: NetworkPolicies drop all outbound traffic from the agent except to the platform gateways.*
```mermaid
---
config:
  theme: neutral
---
flowchart TB
  subgraph Internet[Internet]
    SaaS[External SaaS / APIs]
  end

  subgraph Datastores[Datastores Namespace]
    Postgres[Postgres\nClusterIP]
    Valkey[Valkey\nClusterIP]
  end

  subgraph Platform[Platform Namespace]
    AIGateway[AI Gateway\nClusterIP]
    MCPGateway[MCP Gateway\nClusterIP]
  end

  subgraph Worker[Worker Namespace]
    Agent[Agent Pod\nClusterIP]
  end

  Agent -- "/v1 chat" --> AIGateway
  Agent -- "MCP tools" --> MCPGateway
  
  Agent -.-x|"BLOCKED"| SaaS
  Agent -.-x|"BLOCKED"| Postgres
  Agent -.-x|"BLOCKED"| Valkey
  
  AIGateway --> SaaS
  MCPGateway --> Postgres
```

## The Boundary

You provide the **Agent Code**. The platform generates the **NetworkPolicies** and **Gateways**.

By default, an agent pod cannot open a connection to the internet, nor can it talk directly to the underlying datastores (Postgres, Valkey, Qdrant). All its interactions must go through the platform's AI Gateway for LLM calls and the MCP Gateway for tool calls and data access. This guarantees that observability, guardrails, and tenant isolation cannot be bypassed.
