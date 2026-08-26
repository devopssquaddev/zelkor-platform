# Quick Start

Deploy a production-like Zelkor Platform instance locally in under 5 minutes using Kubernetes IN Docker (`kind`).

## Architecture & Pillars

The Community Edition local development environment deploys all seven core platform pillars:

1. **Monitor (Observability):** Langfuse v2 seeded with golden datasets, prompts, and tracing.
2. **Govern (LLM Gateway):** Official Envoy AI Gateway controller with Gateway API CRDs (`AIGatewayRoute`, `AIServiceBackend`, `BackendSecurityPolicy`), rate limiting, and multi-provider routing (Ollama default, OpenAI, Anthropic, Gemini).
3. **Guardrails:** NeMo Guardrails (CPU) enforcing topical boundaries and compliance.
4. **Deploy (Agent Orchestration):** Aegra Agent Runtime persisted to PostgreSQL and Valkey.
5. **Test (Evaluation):** Langfuse pre-seeded evaluation datasets and test suites (BASE-01 to BASE-05).
6. **Engine (Automation & Sink):** In-cluster engine-sink capturing flagged traces and webhook events.
7. **Semantic Memory & Tool Protocol:** Qdrant vector database with Model Context Protocol (`MCPRoute`) tools and gVisor sandboxed code execution.

## Prerequisites

- macOS (Docker Desktop / OrbStack), Linux, or Windows (WSL2)
- [Docker](https://docs.docker.com/get-docker/)
- [kind](https://kind.sigs.k8s.io/docs/user/quick-start/#installation)
- [Helm](https://helm.sh/docs/intro/install/) 3.x
- [kubectl](https://kubernetes.io/docs/tasks/tools/)

## Install

```bash
git clone https://github.com/devopssquaddev/zelkor-platform.git
cd zelkor-platform
./install.sh
```

The script will:

1. Verify `docker`, `kind`, `helm`, and `kubectl` are available
2. Create a `kind` cluster named `zelkor` (with gVisor container runtime support)
3. Install Envoy Gateway and Envoy AI Gateway controller and CRDs
4. Deploy the unified Helm chart with `values-local.yaml`
5. Deploy the FinServe wealth management demo

## Verify & Access

```bash
kubectl --context kind-zelkor get pods -A
helm --kube-context kind-zelkor list
```

All services and Web UIs are accessible via Kubernetes Gateway API on port `8088`:

| Component | URL | Dev Credentials / Headers |
| :--- | :--- | :--- |
| **Langfuse Observability** | [http://langfuse.localhost:8088](http://langfuse.localhost:8088) | `admin@zelkor.local` / `zelkor-dev-password` (Project: `FinServe AI`) |
| **Envoy AI Gateway** | [http://ai-gateway.localhost:8088](http://ai-gateway.localhost:8088) | `Authorization: Bearer dev-key`, `X-Tenant-ID: Bank_Alpha` |
| **Aegra Agent Runtime** | [http://aegra.localhost:8088/docs](http://aegra.localhost:8088/docs) | `Authorization: Bearer dev:Bank_Alpha` |
| **FinServe Demo Agent** | [http://finserve.localhost:8088/docs](http://finserve.localhost:8088/docs) | `Authorization: Bearer dev:Bank_Alpha` |
| **Native MCP Gateway** | [http://mcp.localhost:8088/mcp](http://mcp.localhost:8088/mcp) | `Authorization: Bearer dev:Bank_Alpha`, `X-Tenant-ID: Bank_Alpha` |

### Instant Observability & Seeding
The local development environment pre-seeds a Langfuse user, organization, API keys, system prompts (`finserve-system`), and golden evaluation datasets (`finserve-eval-dataset`). Requests sent through the Envoy AI Gateway or the FinServe demo agent automatically stream live traces into Langfuse.

## LLM Provider Configuration

By default, the platform routes to local Ollama on `http://host.docker.internal:11434` without requiring any API keys.

To use cloud providers or Ollama Cloud, export environment variables before running `./install.sh`:

```bash
# Ollama Cloud
export OLLAMA_API_KEY="your-ollama-api-key"
export OLLAMA_HOST="https://ollama.com"

# OpenAI / Anthropic / Gemini
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
export GEMINI_API_KEY="AIza..."

./install.sh
```

## Configuration

Local defaults live in `charts/zelkor-platform/values-local.yaml`. Override at install time:

```bash
VALUES_FILE=charts/zelkor-platform/values-local.yaml ./install.sh
```

## Uninstall

```bash
helm --kube-context kind-zelkor uninstall finserve --ignore-not-found
helm --kube-context kind-zelkor uninstall zelkor-platform --ignore-not-found
kind delete cluster --name zelkor
```
