---
title: Helm Values Reference
description: V2 platform, workspace, and workload namespaces, substrate keys, schema validation, and Pro or Enterprise gates.
type: reference
sidebar_group: Reference
sidebar_order: 20
audience: human
edition: all
---

# Helm Values Reference

Chart: `charts/zelkor-platform`. Authoritative defaults: [`values.yaml`](../../charts/zelkor-platform/values.yaml). Install-time validation: [`values.schema.json`](../../charts/zelkor-platform/values.schema.json).

New to Zelkor? Start with [Local Quickstart](../quickstart.md), then use this page when you overlay GitOps values.

Helm rejects unknown keys under documented objects (`additionalProperties: false`). Typos fail at `helm install` / `helm template` with a schema path.

## V2 intent namespaces

Customer-facing configuration is grouped into three layers. Templates compile these onto an internal flat tree at render; do **not** set removed V1 roots (`aiGateway`, `auth`, `langfuse`, `aegra`, `guardrails`, `mcp`, `logging`) — render fails with a migration message.

| Namespace | Owner | Purpose |
| :--- | :--- | :--- |
| `platform.*` | Platform admin | Tenants, JWT/SSO, telemetry (Langfuse), logging level/format, Enterprise mTLS knob |
| `workspace.*` | AI engineering lead | Models (AI Gateway providers), guardrail policies, MCP tool servers and extra backends |
| `workload.*` | Agent developer | Platform Aegra worker settings, default route attachment, MCP inject, per-run intent (Pro approval) |

### `platform`

| Path | Role |
| :--- | :--- |
| `platform.tenants.jwt` | Issuer, audiences, JWKS ConfigMap or remote URI, tenant claims |
| `platform.tenants.sso.enabled` | **Pro** — fails on CE chart without entitlement |
| `platform.tenants.orgMappings` | Map org ids to tenant ids on the Aegra worker |
| `platform.telemetry.level` / `format` | Process log level and JSON/text |
| `platform.telemetry.langfuse` | Langfuse Deployment, init keys, surfaces |
| `platform.telemetry.aegraOtelTargets` | OTEL export targets copied to platform Aegra |
| `platform.mTLS.enabled` | **Enterprise** — fails on CE |

### `workspace`

| Path | Role |
| :--- | :--- |
| `workspace.models.enabled` | AI Gateway route generation |
| `workspace.models.consumerKey` | Shared `/v1` bearer key for agents |
| `workspace.models.defaultModel` | Default model id when unset on the worker |
| `workspace.models.providers.*` | Named LLM backends — see [Add LLM providers](../adding-llm-providers-and-models.md) |
| `workspace.models.providers.openaiCompat[]` | Generic OpenAI-schema hosts (Groq, Mistral, …) |
| `workspace.policies.nemo` | NeMo Guardrails intercept and model |
| `workspace.policies.llamaGuard` | **Enterprise** |
| `workspace.policies.presidio` | **Enterprise** |
| `workspace.tools.enabled` | Unified MCP gateway and native MCP Deployments |
| `workspace.tools.extraBackends[]` | BYO MCP registration — see [Register extra MCP backends](../mcp-extra-backends.md) |
| `workspace.tools.postgresMCP` / `qdrantMCP` / `sandboxMCP` / `aigatewayMCP` | Native MCP settings |

### `workload`

| Path | Role |
| :--- | :--- |
| `workload.agents.enabled` | Platform Aegra Deployment |
| `workload.agents.image` | Platform runtime image tag/digest |
| `workload.agents.attachDefaultRoute` | Catch-all HTTPRoute to platform Aegra |
| `workload.agents.mcpInject.enabled` | Mode B tool binding in the runtime image |
| `workload.agents.graphs` / `workers` | Empty in CE default — customer agents are separate releases |
| `workload.intent` | Timeout, max tokens; `approval` **Pro** only |

## Substrate keys (root level)

Infrastructure the chart owns outside the three intent layers:

| Key | Role |
| :--- | :--- |
| `global.tier` | `oss` on CE; other values require Pro/Ent umbrella |
| `global.imagePullSecrets` | Copied to agent releases by `zelkor deploy` |
| `gateway.*` | Gateway API / Envoy Gateway, `gateway.hosts.*` HTTP hostnames |
| `databases.mode` | `in-cluster-basic` vs operator-backed modes |
| `postgresql`, `valkey`, `clickhouse`, `qdrant`, `seaweedfs` | Datastore pins and URLs |
| `security.networkPolicies` | Agent default-deny egress; gateway allow lists for extra MCP |
| `security.sandbox` | gVisor runtime class for sandbox workers |
| `highAvailability`, `observability` | Replicas and monitoring hooks |

## `extraManifests`

Top-level array of extra Kubernetes objects (maps or templated YAML strings). Rendered after generated manifests. User objects without labels receive `zelkor.io/intent: extraManifests`. Generated resources carry `zelkor.io/intent: <values path>`.

## Community Edition install-time gates

Setting these on the CE chart alone fails render with an upgrade pointer to [Install on an Existing Cluster](../helm-install.md):

| Values path | Tier |
| :--- | :--- |
| `platform.tenants.sso.enabled: true` | Pro |
| `platform.mTLS.enabled: true` | Enterprise |
| `workspace.policies.llamaGuard` | Enterprise |
| `workspace.policies.presidio` | Enterprise |
| `global.tier` ≠ `oss` | Pro/Ent umbrella |
| `workload.intent.approval.enabled` | Pro |

## V1 migration

Supplying a non-empty removed root (for example `--set aiGateway.providers.openai.apiKey=...`) fails before render. Use `workspace.models.providers.openai.apiKey` instead. Message links: [Add LLM providers](../adding-llm-providers-and-models.md), [Helm install](../helm-install.md), [Register extra MCP](../mcp-extra-backends.md).

## Schema-only stubs

[`values.v1-intent-stubs.yaml`](../../charts/zelkor-platform/values.v1-intent-stubs.yaml) lists removed keys for diagnosable schema errors only; it is not merged into chart defaults.

## Related pages

- [Add LLM providers and models](../adding-llm-providers-and-models.md)
- [Register extra MCP backends](../mcp-extra-backends.md)
- [Install on an Existing Cluster](../helm-install.md)
