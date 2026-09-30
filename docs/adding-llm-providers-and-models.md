---
title: Add LLM Providers and Models
description: Wire OpenAI, Anthropic, Vertex, Bedrock, and OpenAI-compat hosts through the Zelkor AI Gateway with Helm overlays.
type: how-to
sidebar_group: Reference
sidebar_order: 10
audience: human
edition: ce
---

# Add LLM Providers and Models

Agents call models through the in-cluster **Envoy AI Gateway** at `/v1`. Provider API keys and cloud credentials live in the platform Helm release, not on agent pods. You declare models under the **workspace** layer; the chart renders `AIServiceBackend` and route matches for each provider you enable.

## Prerequisites

- A running Zelkor platform release ([Install on an Existing Cluster](./helm-install.md) or local [Quickstart](./quickstart.md)).
- `helm` access to upgrade that release in its namespace.
- At least one provider credential (API key, Azure endpoint, AWS keys, or Vertex service account).

## Set a default model (optional)

Pick the model id agents should use when they do not pass one explicitly:

```bash
helm upgrade zelkor-platform charts/zelkor-platform \
  --namespace zelkor \
  --reuse-values \
  --set workspace.models.defaultModel="openai/gpt-4o-mini"
```

Model ids must match a route the chart created for your enabled providers (see table below).

## Enable a named provider

Use `workspace.models.providers.&lt;name&gt;`. Empty strings in chart defaults mean “disabled until you set a credential.”

**OpenAI**

```bash
helm upgrade zelkor-platform charts/zelkor-platform \
  --namespace zelkor \
  --reuse-values \
  --set workspace.models.providers.openai.apiKey="sk-..."
```

Route model ids: `openai/*` or bare OpenAI model names the gateway matches.

**Anthropic**

```bash
helm upgrade zelkor-platform charts/zelkor-platform \
  --namespace zelkor \
  --reuse-values \
  --set workspace.models.providers.anthropic.apiKey="sk-ant-..."
```

**Google AI Studio (Gemini)**

```bash
helm upgrade zelkor-platform charts/zelkor-platform \
  --namespace zelkor \
  --reuse-values \
  --set workspace.models.providers.gemini.apiKey="..."
```

Route model ids: `gemini/*` and `gemini-*`.

**Azure OpenAI**

```bash
helm upgrade zelkor-platform charts/zelkor-platform \
  --namespace zelkor \
  --reuse-values \
  --set workspace.models.providers.azure.apiKey="..." \
  --set workspace.models.providers.azure.endpoint="https://YOUR-RESOURCE.openai.azure.com"
```

Route model ids: `azure/*`. Optional `workspace.models.providers.azure.apiVersion` (chart default `2025-01-01-preview`).

**AWS Bedrock**

```bash
helm upgrade zelkor-platform charts/zelkor-platform \
  --namespace zelkor \
  --reuse-values \
  --set workspace.models.providers.bedrock.accessKeyId="..." \
  --set workspace.models.providers.bedrock.secretAccessKey="..." \
  --set workspace.models.providers.bedrock.region="us-east-1"
```

Route model ids: `bedrock/*`. Set `workspace.models.providers.bedrock.anthropic=true` for Claude on Bedrock (`bedrock-anthropic/*`).

**Cohere**

```bash
helm upgrade zelkor-platform charts/zelkor-platform \
  --namespace zelkor \
  --reuse-values \
  --set workspace.models.providers.cohere.apiKey="..."
```

Route model ids: `cohere/*`.

**Ollama Cloud / local Ollama**

```bash
helm upgrade zelkor-platform charts/zelkor-platform \
  --namespace zelkor \
  --reuse-values \
  --set workspace.models.providers.ollamaCloud.apiKey="..."
```

```bash
helm upgrade zelkor-platform charts/zelkor-platform \
  --namespace zelkor \
  --reuse-values \
  --set workspace.models.providers.ollamaLocal.host="http://ollama.example.svc:11434"
```

**In-cluster vLLM (OpenAI `/v1`)**

```bash
helm upgrade zelkor-platform charts/zelkor-platform \
  --namespace zelkor \
  --reuse-values \
  --set workspace.models.providers.vllm.backendUrl="http://vllm.llm.svc:8000/v1"
```

Route model ids: `vllm/*`. Public TLS hosts with API keys belong in `openaiCompat` instead.

Install scripts (`scripts/install-quickstart.sh`, `./install.sh`) accept the same keys via environment variables (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `AZURE_OPENAI_*`, `AWS_*`, `VERTEX_*`, …) and map them to these paths.

## Vertex credentials

Vertex uses the Envoy `GCPVertexAI` schema. Set project and region, then supply credentials in **one** of these ways.

**Helm inline JSON (lab only — prefer Secrets in production)**

```bash
helm upgrade zelkor-platform charts/zelkor-platform \
  --namespace zelkor \
  --reuse-values \
  --set workspace.models.providers.vertex.project="my-gcp-project" \
  --set workspace.models.providers.vertex.region="us-central1" \
  --set-string workspace.models.providers.vertex.credentialsJson='{"type":"service_account",...}'
```

**Existing Secret (recommended)**

```bash
kubectl -n zelkor create secret generic zelkor-platform-vertex-sa \
  --from-file=service_account.json=./sa.json \
  --dry-run=client -o yaml | kubectl apply -f -

helm upgrade zelkor-platform charts/zelkor-platform \
  --namespace zelkor \
  --reuse-values \
  --set workspace.models.providers.vertex.project="my-gcp-project" \
  --set workspace.models.providers.vertex.region="us-central1" \
  --set workspace.models.providers.vertex.existingSecret="zelkor-platform-vertex-sa"
```

The Secret data key must be exactly **`service_account.json`**. Wrong key names cause token rotation to fail and `gemini-*` requests to return 500 `unknown backend` — see [Vertex gemini unknown backend](kb/ai-gateway-vertex-unknown-backend.md).

**ADC / Workload Identity:** leave `credentialsJson` and `existingSecret` empty when the cluster can obtain GCP credentials without a file.

**Model ids**

| Configuration | Example model ids |
| :--- | :--- |
| Vertex only | bare `gemini-2.5-flash`, `gemini-*` |
| Vertex + AI Studio key | `vertex/*` |
| Vertex + `anthropic: true` | `vertex-anthropic/*` |
| `region: global` | upstream host `aiplatform.googleapis.com` |

## OpenAI-compatible hosts (Groq, Mistral, Together, …)

There is no `providers.groq` key. Add one row per host under `workspace.models.providers.openaiCompat`:

```yaml
workspace:
  models:
    providers:
      openaiCompat:
        - name: groq
          host: api.groq.com
          port: 443
          prefix: /openai/v1
          tls: true
          apiKey: "gsk_..."
          modelMatch: "groq/*"
```

Apply via a values overlay file or `--set-file`. Each item requires `name`, `host`, `prefix`, `modelMatch`, and `apiKey` for the chart to render auth. Calls use `model` ids that match `modelMatch` (for example `groq/llama-3.3-70b-versatile`).

## Consumer key on agents

Agents use OpenAI-compatible clients pointed at the platform AI Gateway base URL. The gateway expects the shared **consumer key** from `workspace.models.consumerKey` (install scripts set this when you pass `AI_GATEWAY_CONSUMER_KEY` or let the script generate one). Do not mount provider API keys on agent Deployments.

How the hop fits the sandbox: [Drop-In Agent Contract](architecture-agent-contract.md).

## Verify

After `helm upgrade` completes, call chat completions through the gateway Host your install configured (`gateway.hosts.aiGateway`):

```bash
curl -sS "https://ai-gateway.example.com/v1/chat/completions" \
  -H "Host: ai-gateway.example.com" \
  -H "Authorization: Bearer ${AI_GATEWAY_CONSUMER_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"model":"openai/gpt-4o-mini","messages":[{"role":"user","content":"ping"}]}'
```

Expect HTTP 200 and a completion body. A 504 often means no backend matched the `model` string; recheck provider enablement and model id prefix.

## Pro and Enterprise (same backends)

Community Edition wires every Envoy AI Gateway provider schema. **Pro** adds `AITeam` allow lists and budgets on the same routes. **Enterprise** adds ESO-backed keys, inbound SSO on `/v1`, and Presidio masking — not different provider adapters.

## See also

- [Helm values reference](reference/helm-values.md) — `workspace.models` and schema validation
- [Vertex unknown backend KB](kb/ai-gateway-vertex-unknown-backend.md)
