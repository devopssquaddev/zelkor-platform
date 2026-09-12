# Production Deployment

This guide covers deploying Zelkor Community Edition to a production Kubernetes environment. 

Unlike the quickstart, the production deployment uses Kubernetes operators to manage highly available (HA) datastores, enables NetworkPolicies for security, and pins container images by digest for repeatable deployments.

## Prerequisites

- Kubernetes v1.28+ with a default StorageClass
- At least **3 Ready worker nodes** (required for PostgreSQL HA)
- `kubectl` v1.28+ and `helm` v3.10+
- **Envoy Gateway** and **Envoy AI Gateway** (see [Gateway Topologies](envoy-gateway-topologies.md))
- **metrics-server** (for Horizontal Pod Autoscaling)
- *(Optional)* S3 bucket for PostgreSQL backups (Barman), cert-manager `ClusterIssuer` for TLS, Prometheus Operator CRDs for monitoring.

*Security Note: Do not use `*.localhost` domains, `dev-key` tokens, or unsigned authentication in production.*

## Layer 1: Install Operators

Zelkor relies on several operators to manage its stateful components. We provide a bootstrap script that installs these operators idempotently (it skips installation if the CRD already exists).

- **CloudNativePG:** Manages highly available PostgreSQL clusters.
- **Altinity ClickHouse Operator:** Manages ClickHouse analytics databases.

```bash
git clone https://github.com/devopssquaddev/zelkor-platform.git
cd zelkor-platform

# Install the required operators
./scripts/bootstrap-operators.sh
```

*(Note: If you are using external managed databases like RDS or Aurora, you can skip this step and set `databases.mode: external` in your Helm values).*

## Layer 1b: Bootstrap Gateways

Install Envoy Gateway and Envoy AI Gateway before the platform chart. Pick the scenario that matches your cluster — see [Gateway Topologies](envoy-gateway-topologies.md) for the full matrix.

**Greenfield or new cluster (default):**

```bash
./scripts/bootstrap-gateway.sh
```

**Existing ingress (NGINX, Traefik, ALB) — layered routing:**

```bash
./scripts/bootstrap-gateway.sh
# Then use -f profiles/values-gateway-layered.yaml when deploying the chart (below)
```

**Envoy Gateway already installed:**

```bash
./scripts/bootstrap-gateway.sh --skip-envoy-gateway --patch-extension-manager
# Then use -f profiles/values-gateway-shared.yaml and set gateway.parentRef.*
```

**Both gateways already installed:**

```bash
./scripts/bootstrap-gateway.sh --skip-envoy-gateway --skip-ai-gateway
```

## Layer 2: Deploy the Platform

Once the operators are running, you can deploy the Zelkor platform chart. This step requires creating a namespace, setting up your LLM provider secret, and providing secure passwords for the datastores.

```bash
# 1. Create the namespace
kubectl create namespace zelkor

# 2. Create the LLM provider secret
kubectl create secret generic zelkor-secrets \
  --namespace zelkor \
  --from-literal=openai-api-key="sk-your-actual-api-key"

# 3. Deploy the platform (add -f profiles/values-gateway-layered.yaml if using layered routing)
helm upgrade --install zelkor-platform charts/zelkor-platform \
  --namespace zelkor \
  -f profiles/values-production.yaml \
  -f profiles/values-gateway-greenfield.yaml \
  --set postgresql.auth.password="secure-pg-password" \
  --set clickhouse.auth.password="secure-ch-password" \
  --set seaweedfs.auth.accessKey="secure-s3-access" \
  --set seaweedfs.auth.secretKey="secure-s3-secret" \
  --set langfuse.nextauthSecret="$(openssl rand -base64 32)" \
  --set langfuse.salt="$(openssl rand -base64 32)" \
  --set langfuse.encryptionKey="$(openssl rand -hex 32)" \
  --set langfuse.nextauthUrl="https://langfuse.yourdomain.com" \
  --set gateway.hosts.agents="agents.yourdomain.com" \
  --set gateway.hosts.langfuse="langfuse.yourdomain.com"
```

### Production Profile Details

The `values-production.yaml` profile enforces the following:
- `databases.mode: operator-cr`
- CloudNativePG instances scaled to 3
- `highAvailability.enabled: true`
- NetworkPolicies enabled

### Optional Configurations

**TLS Configuration:**
If you have cert-manager installed, you can enable TLS by specifying your ClusterIssuer:
```bash
--set gateway.tls.enabled=true \
--set gateway.tls.clusterIssuer=letsencrypt-prod
```

**Monitoring:**
If the Prometheus Operator is present on your cluster:
```bash
--set observability.serviceMonitor.enabled=true
```

**Scaling Gateways:**
For high availability, scale the Envoy controllers (which are installed outside the Zelkor chart):
```bash
kubectl -n envoy-gateway-system scale deploy/envoy-gateway --replicas=2
kubectl -n envoy-ai-gateway-system scale deploy/ai-gateway-controller --replicas=2
```

## Verifying the Deployment

Langfuse automatically generates an admin password if one is not provided during installation. You can retrieve the login credentials from the generated secret:

```bash
# Get Admin Email
kubectl -n zelkor get secret zelkor-platform-langfuse-admin \
  -o jsonpath='{.data.email}' | base64 -d; echo

# Get Admin Password
kubectl -n zelkor get secret zelkor-platform-langfuse-admin \
  -o jsonpath='{.data.password}' | base64 -d; echo
```

Check the status of your operator-managed databases:
```bash
kubectl get cluster,clickhouseinstallation -n zelkor
```

## Deploying Agents in Production

Use the Zelkor CLI to deploy agents to your production cluster. 

```bash
zelkor env add production --kube-context your-prod-context --namespace zelkor
zelkor deploy
```

The first worker deployed acts as the catch-all (Topology 1). Subsequent agents require the `X-Graph-ID` header for routing. Agent deployments are isolated Helm releases, meaning `zelkor logs` and `zelkor undeploy` target only the specific agent, not the underlying platform.
