# Zelkor

> Zelkor is the self-hosted agent runtime for Kubernetes: it runs the LangGraph, Deep Agents, CrewAI, Pydantic AI or other A2A agent you already wrote, and governs its model calls, tool calls, generated code, network and traces. It is not an agent framework: you do not rewrite your agent for it.

Community Edition (Apache-2.0, chart `{{chartVersion}}`) gives each agent:

- No provider key on the agent pod: the agent calls the in-cluster Envoy AI Gateway, which injects the real key.
- A global request cap on the gateway (chart default 50 requests per minute), so a looping agent gets HTTP 429 instead of a bill.
- Generated code runs in a separate sandbox worker pod on RuntimeClass `gvisor`, with no outbound network.
- NetworkPolicies (on in the production install) so the agent reaches only the platform gateways, not the internet or datastores.
- MCP tools behind one MCP gateway, scoped per tenant from the signed tenant JWT.
- One Langfuse trace per run (model, guardrail and tool spans) over OpenTelemetry.
- Tenant isolation on threads, runs and tool data.

Pro adds per-team USD budgets, tool approvals, persistent sandboxes and SSO. Enterprise adds hardware-isolated sandboxes and compliance. Neither is in Community Edition.

## Quickstart (kind, about 5 minutes)

```bash
git clone https://github.com/devopssquaddev/zelkor-platform.git
cd zelkor-platform
OPENAI_API_KEY=sk-... ./install.sh
```

## Deploy your agent

```bash
zelkor deploy -f values.yaml
```

Coding agents: follow [Install the Platform (Agent Guide)](https://docs.zelkor.io/agent-install.md), then [Deploy an Agent (Agent Guide)](https://docs.zelkor.io/agent-deploy.md). Helm values are validated by `charts/zelkor-platform/values.schema.json` and `charts/zelkor-agent/values.schema.json`. All docs in one file: https://docs.zelkor.io/llms-full.txt
