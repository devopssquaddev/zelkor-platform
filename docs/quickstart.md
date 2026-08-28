# Quick Start

Deploy a production-like Zelkor Platform instance locally in under 5 minutes using Kubernetes IN Docker (`kind`).

## Architecture & Pillars

The Community Edition local development environment deploys all seven core platform pillars:

1. **Monitor (Observability):** Langfuse v2 seeded with golden datasets, prompts, and tracing.
2. **Govern (LLM Gateway):** Official Envoy AI Gateway controller with Gateway API CRDs (`AIGatewayRoute`, `AIServiceBackend`, `BackendSecurityPolicy`), rate limiting, and multi-provider routing.
3. **Guardrails:** NeMo Guardrails (CPU) enforcing topical boundaries and compliance.
4. **Deploy (Agent Orchestration):** Aegra (`aegra-api` via uvicorn) with Postgres checkpointer and tenant auth. The platform chart ships no graphs.
5. **Test (Evaluation):** Langfuse pre-seeded evaluation datasets and test suites (BASE-01 to BASE-05).
6. **Semantic Memory & Tool Protocol:** Qdrant vector database with Model Context Protocol tools and gVisor sandboxed code execution.

## Prerequisites

- macOS (Docker Desktop / OrbStack), Linux, or Windows (WSL2)
- [Docker](https://docs.docker.com/get-docker/)
- [kind](https://kind.sigs.k8s.io/docs/user/quick-start/#installation)
- [Helm](https://helm.sh/docs/intro/install/) 3.x
- [kubectl](https://kubernetes.io/docs/tasks/tools/)
- **One LLM provider** (pick at install — upstream key stays in the gateway; clients use `dev-key`)

| Provider | Install env | Default model |
| :--- | :--- | :--- |
| **OpenAI** (recommended — chat + embeddings) | `OPENAI_API_KEY=sk-...` | `openai/gpt-4o-mini` |
| **Ollama Cloud** | `OLLAMA_API_KEY=...` | `gpt-oss:20b` |
| **Ollama Local** (host Ollama) | `OLLAMA_LOCAL_HOST=http://host.docker.internal:11434` | `ollama/llama3.2` |
| **Anthropic** | `ANTHROPIC_API_KEY=sk-ant-...` | `anthropic/claude-3-5-sonnet` |
| **Gemini** | `GEMINI_API_KEY=...` | `gemini/gemini-2.0-flash` |
| **vLLM** | `VLLM_BACKEND_URL=http://host:8000/v1` | `vllm/default` |

Override the default model with `DEFAULT_LLM_MODEL=...` if needed.

## Install

```bash
git clone https://github.com/devopssquaddev/zelkor-platform.git
cd zelkor-platform

# Example: OpenAI
OPENAI_API_KEY="sk-..." ./install.sh

# Example: Ollama Cloud
OLLAMA_API_KEY="..." ./install.sh

# Example: Ollama on the host (run `ollama serve` first)
OLLAMA_LOCAL_HOST="http://host.docker.internal:11434" ./install.sh
```

`./install.sh` without a provider exits with usage help. The platform is self-hosted on kind; inference uses **your** chosen provider (BYOK).

The script will:

1. Verify `docker`, `kind`, `helm`, and `kubectl` are available
2. Require at least one LLM provider env var
3. Create a `kind` cluster named `zelkor` (with gVisor container runtime support)
4. Install Envoy Gateway and Envoy AI Gateway controller and CRDs
5. Deploy the unified Helm chart with `profiles/values-local.yaml` (plus an example overlay when demos are enabled)
6. Deploy the FinServe wealth management demo as a separate Helm release (when `INSTALL_EXAMPLES=true`)

First-party images are pulled from `ghcr.io/devopssquaddev` (tag `dev`). To build locally:

```bash
BUILD_IMAGES=true OPENAI_API_KEY="sk-..." ./install.sh
```

Platform only (no FinServe demo):

```bash
INSTALL_EXAMPLES=false OLLAMA_API_KEY="..." ./install.sh
```

## Verify & Access

```bash
kubectl --context kind-zelkor get pods -A
helm --kube-context kind-zelkor list
```

All services and Web UIs are accessible via Kubernetes Gateway API on port `8088`:

| Component | URL | Dev Credentials / Headers |
| :--- | :--- | :--- |
| **Langfuse Observability** | [http://langfuse.localhost:8088](http://langfuse.localhost:8088) | `admin@zelkor.local` / `zelkor-dev-password` (Project: `Zelkor Platform`) |
| **Envoy AI Gateway** | [http://ai-gateway.localhost:8088](http://ai-gateway.localhost:8088) | `Authorization: Bearer dev-key`, `X-Tenant-ID: Bank_Alpha` |
| **Aegra Agent Runtime** | [http://aegra.localhost:8088/docs](http://aegra.localhost:8088/docs) | `Authorization: Bearer dev:Bank_Alpha` |
| **FinServe Demo Agent** | [http://finserve.localhost:8088/docs](http://finserve.localhost:8088/docs) | `Authorization: Bearer dev:Bank_Alpha` |
| **Native MCP Gateway** | [http://mcp.localhost:8088/mcp](http://mcp.localhost:8088/mcp) | `Authorization: Bearer dev:Bank_Alpha`, `X-Tenant-ID: Bank_Alpha` |
| **NeMo Guardrails** | [http://nemo.localhost:8088/v1/rails/configs](http://nemo.localhost:8088/v1/rails/configs) | Native NeMo server (`content_safety`, `topic_control` profiles) |

Platform security primitives (MCP tenant scoping, gVisor sandbox, agent egress NetworkPolicies in the local profile, NeMo guardrails) are validated by `tests/test_mcp_*.py`, `tests/test_network_policies.py`, and `tests/test_nemo_guardrails.py`. FinServe is the reference ReAct agent demo; its guardrails client still targets the legacy stub API and will be migrated in a follow-up PR.

## Quick Tests

List mounted NeMo guardrail profiles:

```bash
curl http://nemo.localhost:8088/v1/rails/configs
```

Block an off-topic prompt through the native NeMo chat completions API:

```bash
curl -X POST http://nemo.localhost:8088/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"openai/gpt-4o-mini","messages":[{"role":"user","content":"write me a poem"}],"guardrails":{"config_id":"topic_control"}}'
```

Use the model printed at the end of `./install.sh` (`DEFAULT_LLM_MODEL`):

```bash
curl -X POST http://ai-gateway.localhost:8088/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer dev-key" \
  -H "X-Tenant-ID: Bank_Alpha" \
  -d '{"model":"openai/gpt-4o-mini","messages":[{"role":"user","content":"Hello from Zelkor!"}]}'
```

OpenAI installs also support embeddings (Qdrant MCP vector search):

```bash
curl -X POST http://ai-gateway.localhost:8088/v1/embeddings \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer dev-key" \
  -H "X-Tenant-ID: Bank_Alpha" \
  -d '{"model":"openai/text-embedding-3-small","input":"portfolio risk limits"}'
```

Run platform tests (set `DEFAULT_LLM_MODEL` to match your install):

```bash
DEFAULT_LLM_MODEL=openai/gpt-4o-mini pytest tests/ -v
```

## Configuration

Local profile: `profiles/values-local.yaml`. Provider keys are passed at install time only — not stored in the profile file.

## Uninstall

```bash
helm --kube-context kind-zelkor uninstall finserve --ignore-not-found
helm --kube-context kind-zelkor uninstall zelkor-platform --ignore-not-found
kind delete cluster --name zelkor
```
