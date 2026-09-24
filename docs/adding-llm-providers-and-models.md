# Adding LLM providers and models

**Audience:** Customer GitOps, demo charts, and coding agents.  
**Prerequisite:** Platform installed ([agent-install.md](agent-install.md)).

## Contract

All LLM traffic goes through **Envoy AI Gateway** (`*-ai-gateway` Service, `/v1`). Provider API keys live in **platform Helm values** (or install env vars), not on agent pods. Agents use `Authorization: Bearer <aiGateway.consumerKey>` and pass a **model id** on each `/v1/chat/completions` call (or a default env var).

Do **not** change `charts/zelkor-platform/templates/ai-gateway/`, NeMo `content_safety` templates, or intercept routing to add one provider or model. That is product core; customers and demos **overlay values**.

## What to configure (by goal)

| Goal | Configure here | Example |
| :--- | :--- | :--- |
| Enable a first-party provider (OpenAI, Anthropic, Gemini, Ollama, vLLM, Azure, Bedrock, Vertex, Cohere) | Platform overlay: `aiGateway.providers.<name>.*` | `install.sh` / `install-quickstart.sh` env vars; production `--set aiGateway.providers.openai.apiKey=...` |
| Enable an OpenAI-compatible host (Groq, DeepSeek, Together, …) | Platform overlay: `aiGateway.providers.openaiCompat[]` | `name`, `host`, `prefix`, `apiKey`, `modelMatch` (regex for `x-ai-eg-model`) |
| Install / GitOps default model (NeMo pinned rails, Langfuse seed, docs) | `aiGateway.defaultModel` | `gpt-oss:20b`, `openai/gpt-4o-mini` |
| Override NeMo pinned model only | `guardrails.nemo.model` or `guardrails.nemo.selfCheck.model` | Cheaper model for Yes/No self-check |
| Per-agent default model | `charts/zelkor-agent` → `platform.defaultLlmModel` or pod env `DEFAULT_LLM_MODEL` | Demo `examples/*/chart/values.yaml` |
| Per-request model | Request JSON `model` (intercept passthrough) | Agent code / `ChatOpenAI(model=...)` |

When **only** provider keys are set in GitOps, NeMo pinned rails derive the model id from the first enabled provider (same precedence as install scripts). With **multiple** providers, set `aiGateway.defaultModel` explicitly.

NeMo **must not** use the request `model` for self-check Yes/No calls; that stays on the pinned rail model chain. See multi-root spec `internal/plan/requirements_nemo_local_dev.md` §3.3.

## Install scripts (kind / quickstart / production)

Set **one** provider env var (or pair for Azure/Bedrock/Vertex). The installer sets `aiGateway.defaultModel`, `guardrails.nemo.model`, and Langfuse seed model from `DEFAULT_LLM_MODEL` when unset.

```bash
OPENAI_API_KEY=sk-... ./scripts/install-quickstart.sh --namespace zelkor
OLLAMA_API_KEY=... DEFAULT_LLM_MODEL=qwen3:8b ./install.sh
```

## GitOps / manual Helm (platform release only)

```yaml
# customer-overlay.yaml (example)
aiGateway:
  defaultModel: "openai/gpt-4o-mini"
  providers:
    openai:
      apiKey: "<from-secret>"
    openaiCompat:
      - name: groq
        host: api.groq.com
        port: 443
        prefix: groq
        apiKey: "<from-secret>"
        modelMatch: "^(groq/.*)"
        tls: true
```

```bash
helm upgrade --install zelkor-platform charts/zelkor-platform \
  -f profiles/values-production.yaml \
  -f customer-overlay.yaml \
  --namespace zelkor
```

Upstream keys: [helm-install.md](helm-install.md). Provider matrix: multi-root `internal/plan/requirements_ai_gateway_providers.md`.

## Vertex credentials

Enable Vertex with `aiGateway.providers.vertex.project` and `aiGateway.providers.vertex.region` (use `global` for the global Vertex endpoint). Choose **one** auth mode:

| Mode | Helm values | Notes |
| :--- | :--- | :--- |
| Service account JSON in values | `credentialsJson` | Chart creates a Secret with key `service_account.json`. |
| Pre-created Secret | `existingSecret` | Secret **must** contain key `service_account.json` (GCP key JSON). |
| Workload Identity / ADC | Leave `credentialsJson` and `existingSecret` empty | Envoy uses the pod’s default credential chain. |

Create a Secret for GitOps (replace namespace and file path):

```bash
kubectl -n zelkor create secret generic zelkor-platform-vertex-sa \
  --from-file=service_account.json=./sa.json \
  --dry-run=client -o yaml | kubectl apply -f -
```

Then set `aiGateway.providers.vertex.existingSecret` to that Secret name.

Envoy AI Gateway rotates a short-lived token into `ai-eg-bsp-<release>-vertex-gcp` (key `gcpAccessToken`). If the key name is wrong, the JSON is invalid, or GCP rejects the key (`invalid_grant`), the `BackendSecurityPolicy` stays **NotAccepted**, the Vertex backend is omitted from the dataplane config, and `POST /v1/chat/completions` with `model: gemini-*` returns **500** with `unknown backend` in access logs. See [kb/ai-gateway-vertex-unknown-backend.md](kb/ai-gateway-vertex-unknown-backend.md).

## Agent / demo release (not platform core)

| Do | Do not |
| :--- | :--- |
| Set `platform.defaultLlmModel` on `zelkor-agent` | Edit `charts/zelkor-platform/files/nemo-configs/` for one demo |
| Use `model=` in graph code or `DEFAULT_LLM_MODEL` in Deployment env | Add `AIServiceBackend` YAML under `charts/zelkor-platform/templates/` |
| Register extra MCP via `mcp.extraBackends` on a **platform overlay** | Put provider secrets in `charts/zelkor-platform/values.yaml` defaults |

Demos: `examples/<name>/chart/values-platform-overlay.yaml` for platform knobs; agent model in `examples/<name>/chart/values.yaml` (`platform.defaultLlmModel`). See `.cursor/rules/example-charts.mdc`.

## Placement test (coding agents)

Before editing `charts/zelkor-platform/` for a model or provider:

1. Would this change still belong in the platform if every demo under `examples/` were deleted?
2. Is it a **generic knob** with an empty default (e.g. `openaiCompat: []`, `defaultModel: ""`)?
3. If the answer to (1) is **no**, use a demo/customer overlay or `zelkor-agent` values instead.

## Forbidden without a platform product PR

- New hardcoded model ids or provider names in `values.yaml` defaults
- Forking `AIGatewayRoute` / `unknown-model-reject` / NeMo `config.yml.tpl` for one tenant
- `| default "gpt-oss:20b"` (or any provider model) in platform templates
- Patching agents to call OpenAI/Anthropic directly (bypass gateway)
- Using request `model` to drive NeMo self-check (breaks intercept anti-loop contract)

## Verify

1. `helm template` with your overlay — `AIServiceBackend` and route rules include your `modelMatch`.
2. In-cluster: `POST …/v1/chat/completions` with consumer key and chosen `model`.
3. With NeMo intercept on: harmful prompt refused; benign prompt completes (`tests/test_nemo_guardrails.py` patterns).
