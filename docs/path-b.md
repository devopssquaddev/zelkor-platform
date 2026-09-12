# Path B — production Community Edition

Operator-backed Zelkor on customer Kubernetes (`databases.mode: operator-cr`). Kind stays on [`docs/quickstart.md`](quickstart.md) (`./install.sh`).

Routing is **Gateway API + Envoy Gateway** (not Ingress-NGINX). Overlay turns HA and NetworkPolicies on. TLS and Prometheus scrapes are opt-in `--set`. First-party images are `1.0.0`; this overlay pins digest after `scripts/pin-production-digests.sh`.

## Prerequisites

- Kubernetes v1.28+ with a default StorageClass; **3 Ready workers** (CNPG `instances: 3`)
- `kubectl` v1.28+, `helm` v3.10+
- Envoy Gateway + Envoy AI Gateway already installed (same bootstrap as Path A, or your catalog). Envoy Gateway is **required** even if Traefik/nginx/ALB already exists
- **metrics-server** (HPA)
- Optional: S3 bucket for Barman; cert-manager `ClusterIssuer`; Prometheus Operator CRDs

Do not set `*.localhost`, `dev-key`, or unsigned auth on this path.

## Layer 1 — operators

Idempotent. Skips a controller when its CRD exists.

```bash
git clone https://github.com/devopssquaddev/zelkor-platform.git
cd zelkor-platform
./scripts/bootstrap-operators.sh
# ./scripts/bootstrap-operators.sh --skip-cert-manager --skip-cnpg --skip-clickhouse
```

| Pre-installed | Script | Chart emits |
| :--- | :--- | :--- |
| CloudNativePG | Skip | `postgresql.cnpg.io/v1` `Cluster` |
| Altinity ClickHouse Operator | Skip | `ClickHouseInstallation` |
| cert-manager (Gateway API enabled) | Skip | Gateway annotation when `gateway.tls.clusterIssuer` is set |
| RDS / Aurora / shared ClickHouse | No operator | `databases.mode: external` |

ESO and the official Valkey Operator are not installed.

## Layer 2 — platform chart

```bash
kubectl create namespace zelkor
kubectl create secret generic zelkor-secrets \
  --namespace zelkor \
  --from-literal=openai-api-key="..."

helm upgrade --install zelkor-platform charts/zelkor-platform \
  --namespace zelkor \
  -f profiles/values-production.yaml \
  --set postgresql.auth.password=... \
  --set clickhouse.auth.password=... \
  --set seaweedfs.auth.accessKey=... --set seaweedfs.auth.secretKey=... \
  --set langfuse.nextauthSecret=... --set langfuse.salt=... --set langfuse.encryptionKey=... \
  --set langfuse.nextauthUrl=https://langfuse.example.com \
  --set gateway.hosts.agents=agents.example.com \
  --set gateway.hosts.langfuse=langfuse.example.com
```

Overlay contract: `operator-cr`, CNPG 3 instances, `highAvailability.enabled: true`, NetworkPolicies on, empty hosts. Public AI Gateway `/v1` is opt-in (`--set gateway.hosts.aiGateway=...`). Leave `hosts.mcp` / `hosts.nemo` empty.

```bash
# TLS (you create the ClusterIssuer; the chart does not):
#   --set gateway.tls.enabled=true --set gateway.tls.clusterIssuer=letsencrypt-prod
# Prometheus Operator present:
#   --set observability.serviceMonitor.enabled=true

# Envoy Gateway + AI Gateway controllers: scale to 2 (kind ./install.sh stays 1):
#   kubectl -n envoy-gateway-system scale deploy/envoy-gateway --replicas=2
#   kubectl -n envoy-ai-gateway-system scale deploy/ai-gateway-controller --replicas=2
```

Langfuse login is Secret `{release}-langfuse-admin` (generated once if `langfuse.admin.password` is empty). `langfuse.init` stays off.

```bash
kubectl -n zelkor get secret zelkor-platform-langfuse-admin \
  -o jsonpath='{.data.email}' | base64 -d; echo
kubectl -n zelkor get secret zelkor-platform-langfuse-admin \
  -o jsonpath='{.data.password}' | base64 -d; echo
kubectl get cluster,clickhouseinstallation -n zelkor
```

Already-have-ingress: set `gateway.envoyProxy.enabled=true` and `gateway.envoyProxy.service.type=ClusterIP`; preserve `Host` on the front Ingress. Do not install ingress-nginx.

## Agents

`zelkor env add` a kubecontext, then `zelkor deploy`. Topology 1 (first worker) is the catch-all; later agents need `X-Graph-ID`. `zelkor logs` / `zelkor undeploy` target that Helm release only — not the platform.

Workers that share `platform.databaseUrl` share Aegra `runs`. A foreign lease reaper can recover another graph’s expired rows. Redis prefixes isolate enqueue and SSE only. Overlay escape: per-agent `platform.databaseUrl`.

ClickHouse / Valkey HA, Grafana, ClusterIssuer CRs, and Prometheus Operator install are not Community Edition.
