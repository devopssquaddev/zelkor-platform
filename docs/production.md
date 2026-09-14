# Production Deployment

Deploy Zelkor Community Edition to a production Kubernetes environment.

Unlike the evaluation install, production uses operators for HA datastores, enables NetworkPolicies, and pins first-party images by digest.

## Prerequisites

- Kubernetes v1.28+ with a default StorageClass
- At least **3 Ready worker nodes** (required for PostgreSQL HA)
- `kubectl` v1.28+ and `helm` v3.10+
- **metrics-server** (for Horizontal Pod Autoscaling)
- *(Optional)* S3 bucket for PostgreSQL backups (Barman), cert-manager `ClusterIssuer` for TLS, Prometheus Operator CRDs for monitoring.

Do not use `*.localhost` domains, `dev-key` tokens, or unsigned authentication.

Envoy Gateway topologies: [Gateway Topologies](envoy-gateway-topologies.md). Greenfield is the default (Zelkor installs Envoy when missing). If Envoy Gateway is already running, use `--topology layered` (Zelkor ClusterIP Gateway behind your ingress) or `--topology shared` (attach to their Gateway). CE first-party images on GHCR are **public** — no `imagePullSecret` is required. `--image-pull-secret` is optional (private mirror or a later licensed image). `--strict` fails the install on preflight warnings (StorageClass, node count vs Postgres instances, metrics-server).

## Install

```bash
git clone https://github.com/devopssquaddev/zelkor-platform.git
cd zelkor-platform

OPENAI_API_KEY="sk-..." ./scripts/install-production.sh \
  --namespace zelkor \
  --hosts-agents agents.yourdomain.com \
  --hosts-langfuse langfuse.yourdomain.com
```

The script runs `bootstrap-operators.sh` and `bootstrap-gateway.sh`, then Helm with `profiles/values-production.yaml`. Datastore, sandbox worker, and Langfuse crypto secrets are generated when unset and stored in cluster Secrets. Auto-generated `POSTGRES_PASSWORD`, `CLICKHOUSE_PASSWORD`, and `SEAWEEDFS_*` are hex (URL-safe for Langfuse migration URLs). If you set `CLICKHOUSE_PASSWORD` yourself, use a URL-safe value (no `+`, `/`, `=`, `@`, `&`, etc.). Override with `POSTGRES_PASSWORD`, `CLICKHOUSE_PASSWORD`, `SEAWEEDFS_*`, `WORKER_TOKEN`, or `LANGFUSE_*`. `--generate-passwords` also prints them once.

```bash
# Existing ingress (NGINX, Traefik, ALB) — also valid when EG is already running
OPENAI_API_KEY="sk-..." ./scripts/install-production.sh \
  --topology layered \
  --hosts-agents agents.yourdomain.com \
  --hosts-langfuse langfuse.yourdomain.com

# Then point that ingress at Service zelkor-zelkor-platform-dataplane
# in envoy-gateway-system (port 80) and preserve the Host header.

# Existing Envoy Gateway
OPENAI_API_KEY="sk-..." ./scripts/install-production.sh \
  --topology shared \
  --gateway-class your-gateway-class \
  --parent-ref-name your-gateway \
  --parent-ref-namespace your-gateway-namespace \
  --hosts-agents agents.yourdomain.com \
  --hosts-langfuse langfuse.yourdomain.com

# TLS + Prometheus (optional)
OPENAI_API_KEY="sk-..." ./scripts/install-production.sh \
  --hosts-agents agents.yourdomain.com \
  --hosts-langfuse langfuse.yourdomain.com \
  --tls --cluster-issuer letsencrypt-prod \
  --service-monitor
```

Skip operators when you already have CNPG / ClickHouse Operator / cert-manager: `--skip-operators`.

## Manual Helm

### Layer 1: Operators

```bash
./scripts/bootstrap-operators.sh
```

Skip when using managed databases (`databases.mode: external`).

### Layer 1b: Gateways

```bash
./scripts/bootstrap-gateway.sh
```

Layered routing: `./scripts/bootstrap-gateway.sh --skip-envoy-gateway` when EG already exists (no ConfigMap patch), then `-f profiles/values-gateway-layered.yaml`. Point your ingress at `{namespace}-{release}-dataplane` in `envoy-gateway-system`.
Existing Envoy attach: `./scripts/bootstrap-gateway.sh --skip-envoy-gateway --skip-ai-gateway` and `-f profiles/values-gateway-shared.yaml`. `--patch-extension-manager` only when you explicitly want to mutate their EG ConfigMap.

### Layer 2: Platform

```bash
kubectl create namespace zelkor

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

### Production profile

- `databases.mode: operator-cr`
- CloudNativePG instances: 3
- `highAvailability.enabled: true`
- NetworkPolicies enabled

**TLS:** `--set gateway.tls.enabled=true --set gateway.tls.clusterIssuer=letsencrypt-prod`

**Monitoring:** `--set observability.serviceMonitor.enabled=true`

**Scale Envoy controllers:**

```bash
kubectl -n envoy-gateway-system scale deploy/envoy-gateway --replicas=2
kubectl -n envoy-ai-gateway-system scale deploy/ai-gateway-controller --replicas=2
```

## Verifying the Deployment

```bash
kubectl -n zelkor get secret zelkor-platform-langfuse-admin \
  -o jsonpath='{.data.email}' | base64 -d; echo

kubectl -n zelkor get secret zelkor-platform-langfuse-admin \
  -o jsonpath='{.data.password}' | base64 -d; echo

kubectl get cluster,clickhouseinstallation -n zelkor
```

## Deploying Agents

```bash
zelkor env add production --kube-context your-prod-context --namespace zelkor
zelkor deploy
```

The first worker is the catch-all (Topology 1). Later agents need `X-Graph-ID`. `zelkor logs` / `zelkor undeploy` target that agent release only.

## Uninstall

```bash
./scripts/uninstall.sh --namespace zelkor
./scripts/uninstall.sh --namespace zelkor --purge-gateway --purge-operators
# cert-manager is often pre-installed; only with an extra flag:
./scripts/uninstall.sh --purge-cert-manager
```

`--purge-*` removes only components Zelkor recorded at bootstrap (`kube-system/zelkor-bootstrap-ownership`). Use `--force-purge` for installs from before that record existed. `--delete-namespace` drops the release namespace (and PVCs).
