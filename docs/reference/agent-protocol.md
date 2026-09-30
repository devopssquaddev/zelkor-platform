---
title: Agent Protocol
description: Front-door paths, graph ID matching, and fallbacks.
type: reference
sidebar_group: Reference
sidebar_order: 24
audience: human
edition: all
---

# Agent Protocol Reference

The public Agent Protocol front door (`gateway.hosts.agents`) routes standard LangGraph and Aegra API requests. 

## Routing Mechanics

Envoy uses the `X-Graph-ID` header or the `graph_id` query parameter to route traffic to the correct ClusterIP agent deployment.

1. **Match:** Envoy inspects the request for `X-Graph-ID: <id>` or `?graph_id=<id>`.
2. **Route:** If a match is found, Envoy proxies the request to the Kubernetes Service named `<release>-agent-<id>`.
3. **Fallback:** If no graph ID is provided, or the ID does not match any registered route, Envoy forwards the request to the default backend (`<release>-aegra`).

*Note: Envoy does not parse the JSON body to find the graph ID.*

## Common Paths

The front door supports the standard Agent Protocol REST surface. All these paths undergo the routing logic described above.

| Path | Method | Purpose |
| :--- | :--- | :--- |
| `/runs/wait` | POST | Execute a graph synchronously and wait for the final result. |
| `/runs/stream` | POST | Execute a graph and stream events (SSE). |
| `/threads` | POST | Create a new memory thread. |
| `/threads/{thread_id}/state` | GET | Retrieve the current state of a thread. |
| `/threads/{thread_id}/history` | GET | Retrieve the run history of a thread. |

## Authentication

Authentication is **not** performed at the Envoy ingress layer. Envoy passes the `Authorization` header directly to the destination agent worker. 

The agent worker (wrapped by Aegra) validates the Tenant JWT or development token before executing the graph or communicating with the MCP gateway.
