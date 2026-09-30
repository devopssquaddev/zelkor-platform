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

Zelkor is a self-hosted runtime for AI agents on Kubernetes. You set a **model**, a **tool**, and an **agent**; those same objects run from the laptop Community Edition install to a shared cluster. Bring the agent you already wrote; it is sandboxed — it can't break out, reach unauthorized data or networks, its prompts are verified, budget controlled, and it is under observation.

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

## Agents and examples

| Page | Job |
| :--- | :--- |
| [`zelkor` CLI](../cli/README.md) | Point the CLI at a cluster, deploy your agent, run, inspect |
| [FinServe example](../examples/finserve/README.md) | Optional reference agents (not required to learn the platform) |

## Troubleshooting

| Page | Job |
| :--- | :--- |
| [Vertex `gemini-*` unknown backend](kb/ai-gateway-vertex-unknown-backend.md) | Fix AI Gateway 500 when Vertex auth rotation skips the backend |

Honest POC path: finish [Local Quickstart](quickstart.md), then run the same CE charts on a shared cluster. Production Helm topologies and architecture pages are not published yet — use the CLI and examples above until they are.
