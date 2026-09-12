# Existing Cluster Deployment (Non-Production)

Evaluate Zelkor Community Edition on a cluster you already have (EKS, GKE, AKS, or a shared development cluster) without operators or HA.

This path uses `databases.mode: in-cluster-basic` (in-chart StatefulSets). For a laptop `kind` cluster, see [Local Quickstart](quickstart.md). For HA production, see [Production Deployment](production.md).

## Prerequisites

- An existing Kubernetes cluster (v1.28+)
- `kubectl` and `helm` installed and configured for that cluster
- An LLM provider API key (OpenAI, Anthropic, Gemini, Ollama, or vLLM)

Envoy Gateway and Envoy AI Gateway are installed automatically when missing (greenfield). If Envoy Gateway is **already running**, greenfield/layered **will not** replace `envoy-gateway-config` (that restarts EG). Use `--topology shared` — see [Gateway Topologies](envoy-gateway-topologies.md). `--patch-extension-manager` is an explicit, cluster-wide mutate.

## Install

```bash
git clone https://github.com/devopssquaddev/zelkor-platform.git
cd zelkor-platform

OPENAI_API_KEY="sk-..." ./scripts/install-quickstart.sh --namespace zelkor-play
```

The script bootstraps Envoy (if needed), generates Langfuse secrets, and deploys `profiles/values-quickstart.yaml`. Default play hosts are `agents.<namespace>.zelkor.local` and `langfuse.<namespace>.zelkor.local`. Override with `--hosts-agents` / `--hosts-langfuse`.

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

LANGFUSE_SECRET=$(openssl rand -base64 32)
LANGFUSE_SALT=$(openssl rand -base64 32)
LANGFUSE_ENCRYPTION_KEY=$(openssl rand -hex 32)

helm upgrade --install zelkor-platform charts/zelkor-platform \
  -f profiles/values-quickstart.yaml \
  -f profiles/values-gateway-greenfield.yaml \
  --set aiGateway.providers.openai.apiKey="sk-your-llm-api-key" \
  --set gateway.hosts.agents=agents.zelkor.local \
  --set gateway.hosts.langfuse=langfuse.zelkor.local \
  --set langfuse.nextauthSecret="${LANGFUSE_SECRET}" \
  --set langfuse.salt="${LANGFUSE_SALT}" \
  --set langfuse.encryptionKey="${LANGFUSE_ENCRYPTION_KEY}"
```

Use `--set aiGateway.providers.openai.apiKey` (or anthropic / gemini / ollamaCloud). Do not put the upstream provider key in `aiGateway.consumerKey`.

## Next Steps

```bash
pip install -e ./cli
zelkor env add my-cluster --kube-context your-kube-context --namespace zelkor-play
```

Point DNS or `/etc/hosts` at the Envoy dataplane Service for the agent and Langfuse hosts printed by the script.

## Uninstall

```bash
./scripts/uninstall.sh --namespace zelkor-play
# Also remove Zelkor-owned Envoy (only if this install created it):
./scripts/uninstall.sh --namespace zelkor-play --delete-namespace --purge-gateway
```

Default is Helm uninstall only. `--purge-gateway` / `--purge-operators` skip components Zelkor did not record as installed, unless `--force-purge`. cert-manager is never removed by `--purge-operators`.
