---
title: Documentation
description: Map of published Zelkor docs — quickstart, CLI, examples, and KB.
type: explanation
sidebar_group: Get started
sidebar_order: 1
audience: human
edition: all
---

# Documentation

Zelkor is a self-hosted runtime for AI agents on Kubernetes. You set a **model**, a **tool**, and an **agent**; those same objects run from the laptop Community Edition install to a shared cluster. Bring the agent you already wrote; it is sandboxed — it can't break out, reach unauthorized data or networks, its prompts are verified, budget controlled, and it is under observation; tenants stay isolated (the agent cannot pick another tenant, see the [tenant hop](architecture-tenants.md)).

## Editions

| Edition | What you get |
| :--- | :--- |
| **Community Edition** | Self-hosted runtime in this repository (gateway, tools, sandbox, traces) |
| **Pro** | SSO, team controls (budgets and approvals), production HA / GitOps |
| **Enterprise** | Isolation and compliance on Pro (hardware sandbox, mTLS, retained audit, BAA) |

Start with Community Edition. Pro and Enterprise layers sit on the same platform shape.

## Get started

| Page | Job |
| :--- | :--- |
| [Local Quickstart](quickstart.md) | Install CE on kind, call a model, open a trace |
| [Root README](../README.md) | Product overview and three-command install |

## Install

| Page | Job |
| :--- | :--- |
| [Install on an Existing Cluster](helm-install.md) | Evaluate CE via Helm on a shared cluster |
| [Production Install](production.md) | Deploy the highly available shape of CE with HA operators |
| [Uninstall](uninstall.md) | Remove the platform from your cluster |
| [Upgrade](upgrade.md) | Upgrade the platform chart safely |
| [Customize Guardrails](nemo-guardrails.md) | Add custom NeMo safety policies |
| [Gateway Topologies](topologies.md) | How Envoy Gateway integrates with your cluster |

## Agents and examples

| Page | Job |
| :--- | :--- |
| [Install the Platform (Agent Guide)](agent-install.md) | How coding agents install/uninstall the platform |
| [Deploy an Agent (Agent Guide)](agent-deploy.md) | How coding agents deploy/remove customer agents |
| [Use the zelkor CLI](cli.md) | Env targets, deploy, run, logs, doctor |
| [Register extra MCP backends](mcp-extra-backends.md) | BYO ClusterIP MCP on the unified gateway |
| [FinServe example](../examples/finserve/README.md) | Optional reference agents (not required to learn the platform) |

## Reference

| Page | Job |
| :--- | :--- |
| [Add LLM providers and models](adding-llm-providers-and-models.md) | Helm overlays for AI Gateway backends and model ids |
| [Helm values reference](reference/helm-values.md) | `platform` / `workspace` / `workload` namespaces and schema |
| [Hosts and Routing](reference/hosts.md) | `gateway.hosts.*` vs internal ClusterIP names |
| [Worker Environment](reference/worker-env.md) | Injected env vars (`OPENAI_BASE_URL`, `MCP_URL`, OTEL) |
| [MCP Tools Reference](reference/mcp-tools.md) | Tool prefixes, extraBackends fields, and list mechanics |
| [Agent Protocol](reference/agent-protocol.md) | Front-door paths, graph ID matching, and fallbacks |
| [Tenants](reference/tenants.md) | Claims, org map, filters vs forwarded, `zelkor token mint` fields |
| [Platform Logging](reference/logging.md) | Stdout JSON structure, levels, and environment variables |

## Architecture

| Page | Job |
| :--- | :--- |
| [Architecture Hub](architecture.md) | Map of all hops, components, and trust boundaries |
| [Request Path](architecture-request-path.md) | How a client call reaches the model |
| [Network Boundaries](architecture-network.md) | Who may talk to whom inside the cluster |
| [Sandbox Isolation](architecture-sandbox.md) | Where generated code executes |
| [MCP Governance](architecture-mcp.md) | How a tool call is isolated and authenticated |
| [Run Trace](architecture-trace.md) | What one run looks like in Langfuse |
| [Drop-In Agent Contract](architecture-agent-contract.md) | How Zelkor sandboxes and governs your agent (Intercept, Wrap, MCP) |
| [Envoy Graph Routing](architecture-routing.md) | How Envoy routes incoming calls to the correct agent deployment |
| [North-South Exposure](architecture-exposure.md) | What Zelkor publishes to the internet versus what stays inside the cluster |
| [Tenant Isolation](architecture-tenants.md) | How one tenant identity is applied on a run |
| [Agent Datastores](architecture-datastores.md) | Stateful infrastructure (Postgres, Qdrant) and BYO options |

## Troubleshooting (KB)

| Page | Job |
| :--- | :--- |
| [Knowledge Base](kb/README.md) | Index of known issues and fixes |
| [Vertex `gemini-*` unknown backend](kb/ai-gateway-vertex-unknown-backend.md) | Fix AI Gateway 500 when Vertex auth rotation skips the backend |

Read [Install on an Existing Cluster](helm-install.md) and [Production Install](production.md) when you are ready to move off kind.
