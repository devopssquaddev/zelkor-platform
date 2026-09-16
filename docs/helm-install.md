# Existing Cluster Deployment (Non-Production)

Evaluate Zelkor Community Edition on a cluster you already have (EKS, GKE, AKS, or a shared development cluster) without operators or HA.

This path uses `databases.mode: in-cluster-basic` (in-chart StatefulSets). For a laptop `kind` cluster, see [Local Quickstart](quickstart.md). For HA production, see [Production Deployment](production.md).

## Prerequisites

- An existing Kubernetes cluster (v1.28+)
- `kubectl` and `helm` installed and configured for that cluster
- An LLM provider API key (OpenAI, Anthropic, Gemini, Ollama, or vLLM)

Envoy Gateway and Envoy AI Gateway are installed automatically when missing (greenfield). Greenfield **refuses** when Envoy Gateway is already running and was not installed by Zelkor. **Layered** is the path when you already have an ingress (or EG) and want Zelkor to create its own ClusterIP Gateway — it does not replace `envoy-gateway-config`. **Shared** attaches routes to **your** Gateway CR. See [Gateway Topologies](envoy-gateway-topologies.md). `--patch-extension-manager` is an explicit, cluster-wide mutate.

## Install

```bash
git clone https://github.com/devopssquaddev/zelkor-platform.git
cd zelkor-platform

OPENAI_API_KEY="sk-..." ./scripts/install-quickstart.sh --namespace zelkor-play
```

The script bootstraps Envoy (if needed), generates install secrets (datastores, sandbox worker token, Langfuse crypto) into cluster Secrets, and deploys `profiles/values-quickstart.yaml`. Override with `POSTGRES_PASSWORD`, `WORKER_TOKEN`, `LANGFUSE_*`, and the other env names listed in `install-production.sh`. Default play hosts are `agents.<namespace>.zelkor.local` and `langfuse.<namespace>.zelkor.local`. Override with `--hosts-agents` / `--hosts-langfuse`. CE GHCR images are public; `--image-pull-secret` is optional.

```bash
# Layered behind existing ingress (NGINX, Traefik, ALB)
OPENAI_API_KEY="sk-..." ./scripts/install-quickstart.sh --topology layered

# Attach to an existing Envoy Gateway
OPENAI_API_KEY="sk-..." ./scripts/install-quickstart.sh --topology shared \
  --gateway-class your-gateway-class \
  --parent-ref-name your-gateway \
  --parent-ref-namespace your-gateway-namespace
```

## Manual Helm

```bash
./scripts/bootstrap-gateway.sh

# Prefer install-quickstart.sh (generates datastore + worker + Langfuse secrets).
# Manual Helm still requires those --set values (or existing cluster Secrets on upgrade).

helm upgrade --install zelkor-platform charts/zelkor-platform \
  -f profiles/values-quickstart.yaml \
  -f profiles/values-gateway-greenfield.yaml \
  --set aiGateway.providers.openai.apiKey="sk-your-llm-api-key" \
  --set gateway.hosts.agents=agents.zelkor.local \
  --set gateway.hosts.langfuse=langfuse.zelkor.local \
  --set postgresql.auth.password="..." \
  --set clickhouse.auth.password="..." \
  --set seaweedfs.auth.accessKey="..." --set seaweedfs.auth.secretKey="..." \
  --set langfuse.nextauthSecret="..." --set langfuse.salt="..." \
  --set langfuse.encryptionKey="$(openssl rand -hex 32)"
```

Use `--set aiGateway.providers.openai.apiKey` (or anthropic / gemini / ollamaCloud / azure / bedrock / vertex / cohere). Extra OpenAI-compat hosts: `aiGateway.providers.openaiCompat`. Model ids are prefix-namespaced (`azure/*`, `vertex/*`, `bedrock/*`, `cohere/*`). Do not put the upstream provider key in `aiGateway.consumerKey`.

## Next Steps

```bash
pip install -e ./cli
zelkor env add my-cluster --kube-context your-kube-context --namespace zelkor-play
```

Point DNS or `/etc/hosts` at the Envoy dataplane Service `{namespace}-{release}-dataplane` in `envoy-gateway-system` (printed by the script). For layered installs, point your existing ingress at that ClusterIP Service and preserve the Host header. Zelkor does not create Ingress objects.

## Uninstall

```bash
./scripts/uninstall.sh --namespace zelkor-play
# Also remove Zelkor-owned Envoy (only if this install created it):
./scripts/uninstall.sh --namespace zelkor-play --delete-namespace --purge-gateway
```

Default is Helm uninstall only. `--purge-gateway` / `--purge-operators` skip components Zelkor did not record as installed, unless `--force-purge`. cert-manager is never removed by `--purge-operators`. Missing Helm releases are skipped (no `helm uninstall --ignore-not-found`; Helm 3.10+).
