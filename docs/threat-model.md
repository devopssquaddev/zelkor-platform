---
title: Zelkor Platform Threat Model
description: The assets we protect, trust boundaries we enforce, and security promises we make.
type: explanation
sidebar_group: Architecture
sidebar_order: 15
audience: human
edition: all
---

# Zelkor Platform Threat Model

This document outlines the threat model for the Zelkor Platform Community Edition (CE). It defines the assets we protect, the trust boundaries we enforce, and the security promises we make. 

## 1. Assets

| Id | Asset | Owner of harm |
| :--- | :--- | :--- |
| A1 | Tenant data: threads, runs, checkpointer state, SQL rows, vector points, object keys | Customer's tenant |
| A2 | Provider API keys, JWT signing secret, worker token, datastore credentials | Operator |
| A3 | Node and cluster control plane (host kernel, kubelet, Kubernetes API) | Operator |
| A4 | Egress reputation and cost (internet, LLM spend) | Operator |
| A5 | Traces and logs (may contain prompts, identities) | Customer + operator |
| A6 | Guardrail policy (safety rails, model allow-list) | Operator |

Platform datastores hold these assets and are reachable only by their owning components, never directly by an agent pod: Postgres, ClickHouse, Valkey, Qdrant.

## 2. Trust Boundaries

| Id | Boundary | Enforced by |
| :--- | :--- | :--- |
| B1 | Internet → public hosts | Gateway API routes, JWT |
| B2 | Tenant ↔ tenant at the API | Tenant authentication |
| B3 | Agent → model | AI Gateway, safety intercept |
| B4 | Agent → tools | MCP gateway, identity inject, backend verify |
| B5 | Generated code → node | gVisor worker, worker token |
| B6 | Pod → pod / internet | NetworkPolicies, agent namespaces |
| B7 | Platform → observability | Log/trace redaction, trace projects |
| B8 | Shipped chart → customer cluster | Chart defaults, schema |

### Standing assumption — white-box attacker (Kerckhoffs)

Every potential attacker is assumed to have full knowledge of how Zelkor works. CE is open-source, and our source code, charts, images, and documentation are not obfuscated. Security rests **only** on:
- **Runtime secrets** — provider keys, JWT signing secret, worker token, datastore credentials.
- **Enforced controls** — JWT verification, identity injection, NetworkPolicies, container sandboxing.

There is no security through obscurity. A control that depends on the attacker not knowing an internal detail is not a security control.

## 3. Security Promises (CE)

When deployed in a production configuration ([NetworkPolicies](architecture-network.md) enabled, no development tokens or header-trust overrides), Zelkor CE is designed and tested to ensure the following:

- **Tenant Isolation:** Tenant B cannot get, search, or stream Tenant A's threads or runs (see [Tenant Isolation](architecture-tenants.md)).
- **Authentication:** Unsigned requests, invalid tokens, or missing tenant identities are rejected.
- **Model Gateway:** Every agent LLM call uses the in-cluster AI Gateway. Completions cannot bypass the gateway to reach the provider directly.
- **Tool Identity:** Tool call tenant identity is injected by the platform. The model, client, or agent environment cannot override it.
- **Database MCP:** Identity matching and tenant scoping are enforced. Arbitrary writes via the query interface are rejected.
- **Vector MCP:** Vector upsert and search operations are forced to use the caller's tenant filter.
- **Code Execution:** Untrusted code execution runs in a [gVisor sandbox](architecture-sandbox.md).
- **Network Isolation:** Agent pods cannot reach platform datastores, sandbox workers, extra-backend services, or the public internet except through the AI Gateway and MCP gateway.
- **Exposure:** Production installs expose no public routes for internal services (e.g., databases, native MCPs, safety rails) (see [North-South Exposure](architecture-exposure.md)).
- **Guardrails:** Enabled safety and topic rails refuse in-scope harmful or off-topic content.
- **Observability:** INFO+ logs and default traces do not contain credentials or prompt bodies. Provider keys live in platform secrets, not agent pod environments.

## 4. What CE Does Not Isolate (NON List)

Transparency is a core security principle. The following items are explicitly **not** claimed as isolated or enforced in the Community Edition. This list signals maturity: we state our limits honestly rather than overclaiming.

| Id | Not a CE promise | Honest statement |
| :--- | :--- | :--- |
| N1 | Automatic Postgres RLS / `WHERE` rewrite | Policies are the customer's responsibility; without them, SQL queries can read other tenants' rows. |
| N2 | Isolation of a database dump or shared checkpointer | The platform uses a single database; isolation relies on application-level filtering. |
| N3 | Isolation of a trace database dump or org-admin UI | Per-project keys isolate trace listing; raw database dumps do not. |
| N4 | SaaS / extra-backend row security | Headers are forwarded; Zelkor does not enforce SaaS Row-Level Security (RLS). |
| N5 | Deep Agents in-memory file tools are gVisor | Only the dedicated code execution sandbox worker uses gVisor. |
| N6 | Header-only tenant authentication | Header-only trust is for development only and is not production-safe. |
| N7 | Public MCP or public safety rails | These are not supported production surfaces; they must remain internal cluster services. |

## 5. CE vs. Enterprise Edition

Certain security and compliance features are reserved for the Enterprise Edition (Ent). We state these differences as facts:

- **Sandboxing:** CE uses gVisor for untrusted execution. Enterprise offers Kata Containers.
- **Database Isolation:** CE relies on application-level tenant filtering (N1, N2). Enterprise provides automatic Postgres Row-Level Security (RLS) for state tables.
- **Network Security:** NetworkPolicies (NP) must be enabled in production for CE. Enterprise adds pod-to-pod mTLS.
- **Identity & Audit:** Inbound SSO (OIDC) and structured audit logging (SIEM integration) are Enterprise features.
