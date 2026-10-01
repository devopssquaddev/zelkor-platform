---
title: Deploy an Agent (Agent Guide)
description: How to deploy and remove a customer agent on the Zelkor platform.
type: how-to
sidebar_group: Agents
sidebar_order: 2
audience: agent
edition: ce
---

# Deploy an Agent (Agent Guide)

This guide is for coding agents. It explains how to deploy and remove a customer agent on the Zelkor platform.

Zelkor's core advantage: **bring the agent you already wrote; it is sandboxed — it can't break out, reach unauthorized data or networks, its prompts are verified, budget controlled, and it is under observation.**

Zelkor uses a **ClusterIP** worker pattern. Each independently released agent is its own Kubernetes Deployment, built from the Zelkor Aegra runtime image. The platform's Envoy Gateway routes incoming Agent Protocol calls to the correct worker based on the `X-Graph-ID` header.

## Deploying via GitOps (Helm)

The recommended way to deploy a customer agent is using the `zelkor-agent` Helm chart. This chart creates the ClusterIP Deployment and registers it with the platform's front door.

1. **Build the agent image.** The image must extend `ghcr.io/devopssquaddev/zelkor-aegra` (or `zelkor-aegra-deep` for deploy-first Deep Agents).
2. **Create a values file** (e.g., `agent-values.yaml`) for the `zelkor-agent` release.

```yaml
graphId: "my-agent-id"

sharedRoute:
  host: "agents.example.com"

image:
  repository: my-registry/my-agent
  tag: "2.1.1"

platform:
  # The name of the platform Helm release (e.g., zelkor-platform).
  # This allows the agent to inherit the platform's checkpointer, Valkey, and Langfuse OTEL config.
  releaseName: "zelkor-platform"

# Isolate the agent's job queue and SSE channels on the shared Valkey.
redis:
  prefix: "aegra:my-agent"
```

> **Note on Keys:** Do not supply provider API keys (e.g. `OPENAI_API_KEY`) in the agent values. Actual provider keys belong in the platform's AI Gateway configuration (`workspace.models.providers...`), not on the agent worker.

3. **Install the Helm release.**

```bash
helm upgrade --install my-agent charts/zelkor-agent \
  --namespace zelkor \
  --values agent-values.yaml
```

The agent will self-register with the platform's Envoy Gateway on `agents.example.com`. Clients must pass `X-Graph-ID: my-agent-id` to reach this worker. For a complete example of a worker values file, see the [FinServe slim-worker overlay](../examples/finserve/chart/values.yaml).

## Deploying via CLI

The `zelkor` CLI provides a streamlined way to build and deploy agents without writing Helm values.

```bash
# Ensure the CLI is pointed at the correct cluster and namespace
zelkor env add production --kube-context my-context --namespace zelkor
zelkor env use production

# Build and deploy the agent
zelkor deploy --timeout 60s
```

The `deploy` command builds the image, pushes it to the registry, and runs `helm upgrade` on the `zelkor-agent` chart. It automatically copies the platform's Langfuse OTEL configuration so your traces appear in the Langfuse UI, and it wires up the platform's MCP gateway so your agent can use native tools or registered extra backends.

## Run Your Agent

To test your deployed agent, use the `zelkor run` CLI command or a direct curl.

```bash
zelkor run --graph-id my-agent-id --input "What is my portfolio valuation?"
```

Or via curl to the Envoy front door (requires a valid JWT or dev token):

```bash
curl -X POST https://agents.example.com/runs/wait \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your-token>" \
  -H "X-Graph-ID: my-agent-id" \
  -d '{
    "assistant_id": "my-agent-id",
    "graph_id": "my-agent-id",
    "input": {
      "messages": [{"role": "human", "content": "What is my portfolio valuation?"}]
    }
  }'
```

After the run completes, visit the Langfuse UI (`langfuse.example.com`) to inspect the trace. Envoy routes on `X-Graph-ID` (or `?graph_id=`), not the JSON body. The run body still needs `assistant_id`. If Aegra returns 422 `assistant_id` Field required, see [runs/wait assistant_id](kb/runs-wait-assistant-id.md).

## Removing an Agent

To remove an agent deployed via Helm:

```bash
helm uninstall my-agent --namespace zelkor
```

To remove an agent deployed via the CLI:

```bash
zelkor undeploy
```

This removes the agent's Deployment and its HTTPRoute registration, restoring the platform's default routing behavior for that graph ID.