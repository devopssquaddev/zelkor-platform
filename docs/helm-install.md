# Existing Cluster Deployment (Non-Production)

If you already have a Kubernetes cluster (such as EKS, GKE, AKS, or a shared development cluster) and want to evaluate Zelkor Community Edition without setting up the full production stack (operators, HA, etc.), you can deploy the platform using standard Helm commands.

This deployment method uses the `in-cluster-basic` database mode, which provisions simple StatefulSets for datastores rather than requiring dedicated operators.

For local laptop deployments, see the [Local Quickstart](quickstart.md). For highly available production deployments, see [Production Deployment](production.md).

## Prerequisites

- An existing Kubernetes cluster (v1.28+)
- `kubectl` and `helm` installed locally and configured to access your cluster
- An LLM provider API key (e.g., OpenAI, Anthropic)

## Step 1: Bootstrap Gateways

Zelkor requires Envoy Gateway and Envoy AI Gateway. See [Gateway Topologies](envoy-gateway-topologies.md) if your cluster already runs either component.

```bash
git clone https://github.com/devopssquaddev/zelkor-platform.git
cd zelkor-platform

# Install both (greenfield eval cluster)
./scripts/bootstrap-gateway.sh
```

For shared-gateway attach mode, use `profiles/values-gateway-shared.yaml` and the skip flags described in the topology doc.

## Step 2: Deploy via Helm

Use `values-quickstart.yaml` for basic in-cluster evaluation. Provide your LLM API key and Langfuse secrets.

```bash
LANGFUSE_SECRET=$(openssl rand -base64 32)
LANGFUSE_SALT=$(openssl rand -base64 32)
LANGFUSE_ENCRYPTION_KEY=$(openssl rand -hex 32)

helm upgrade --install zelkor-platform charts/zelkor-platform \
  -f profiles/values-quickstart.yaml \
  -f profiles/values-gateway-greenfield.yaml \
  --set aiGateway.consumerKey="sk-your-llm-api-key" \
  --set langfuse.nextauthSecret="${LANGFUSE_SECRET}" \
  --set langfuse.salt="${LANGFUSE_SALT}" \
  --set langfuse.encryptionKey="${LANGFUSE_ENCRYPTION_KEY}"
```

*Note: Seed jobs (which populate Langfuse with initial data) will not run until both `langfuse.init.enabled` is true and `aiGateway.consumerKey` is provided.*

## Next Steps

Configure the Zelkor CLI for your cluster:

```bash
pip install -e ./cli
zelkor env add my-cluster --kube-context your-kube-context --namespace default
```
