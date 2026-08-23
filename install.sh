#!/usr/bin/env bash
# Zelkor Platform — local bootstrap (Base Tier)
# Deploys a production-like kind cluster with the unified Helm chart and examples.
#
# Usage:
#   ./install.sh
#
# Prerequisites: docker, kind, helm, kubectl

set -euo pipefail

CLUSTER_NAME="${CLUSTER_NAME:-zelkor}"
CHART_PATH="${CHART_PATH:-charts/zelkor-platform}"
VALUES_FILE="${VALUES_FILE:-${CHART_PATH}/values-local.yaml}"
KIND_CONFIG="${KIND_CONFIG:-kind-config.yaml}"
INSTALL_EXAMPLES="${INSTALL_EXAMPLES:-true}"
FINSERVE_CHART_PATH="${FINSERVE_CHART_PATH:-examples/finserve/chart}"
FINSERVE_VALUES_FILE="${FINSERVE_VALUES_FILE:-${FINSERVE_CHART_PATH}/values-local.yaml}"

log() { echo "[install] $*"; }
die() { echo "[install] ERROR: $*" >&2; exit 1; }

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Missing prerequisite: $1"
}

log "Checking prerequisites..."
require_cmd docker
require_cmd kind
require_cmd helm
require_cmd kubectl

if ! docker info >/dev/null 2>&1; then
  die "Docker is not running. Start Docker and retry."
fi

if ! kind get clusters 2>/dev/null | grep -qx "$CLUSTER_NAME"; then
  log "Creating kind cluster: $CLUSTER_NAME"
  if [[ -f "$KIND_CONFIG" ]]; then
    kind create cluster --name "$CLUSTER_NAME" --config "$KIND_CONFIG"
  else
    kind create cluster --name "$CLUSTER_NAME"
  fi

  # Install runsc (gVisor) binary on kind control plane node
  log "Configuring gVisor (runsc) on kind node..."
  docker exec "${CLUSTER_NAME}-control-plane" sh -c "curl -fsSL https://storage.googleapis.com/gvisor/releases/release/latest/x86_64/runsc -o /usr/local/bin/runsc && curl -fsSL https://storage.googleapis.com/gvisor/releases/release/latest/x86_64/containerd-shim-runsc-v1 -o /usr/local/bin/containerd-shim-runsc-v1 && chmod a+rx /usr/local/bin/runsc /usr/local/bin/containerd-shim-runsc-v1 && /usr/local/bin/runsc install && systemctl restart containerd" || true
else
  log "Kind cluster already exists: $CLUSTER_NAME"
fi

kubectl cluster-info --context "kind-${CLUSTER_NAME}" >/dev/null

if [[ ! -f "$VALUES_FILE" ]]; then
  die "Values file not found: $VALUES_FILE"
fi

KCTX="kind-${CLUSTER_NAME}"

# Ensure ingress-nginx is deployed
log "Deploying NGINX Ingress Controller for kind..."
kubectl apply --context "$KCTX" -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml

log "Waiting for Ingress controller readiness..."
kubectl --context "$KCTX" wait --namespace ingress-nginx \
  --for=condition=ready pod \
  --selector=app.kubernetes.io/component=controller \
  --timeout=5m

log "Waiting for Ingress admission webhook..."
kubectl --context "$KCTX" wait --namespace ingress-nginx \
  --for=condition=complete job --all \
  --timeout=2m || true

log "Applying Platform Helm chart from $CHART_PATH..."
helm upgrade --install zelkor-platform "$CHART_PATH" \
  --kube-context "$KCTX" \
  -f "$VALUES_FILE"

log "Tracking platform rollout progress..."
log "  -> [1/4] Databases (PostgreSQL, Valkey, ClickHouse, Qdrant)..."
kubectl --context "$KCTX" rollout status statefulset/zelkor-platform-postgresql --timeout=5m
kubectl --context "$KCTX" rollout status deployment/zelkor-platform-valkey --timeout=5m
kubectl --context "$KCTX" rollout status statefulset/zelkor-platform-clickhouse --timeout=5m
kubectl --context "$KCTX" rollout status statefulset/zelkor-platform-qdrant --timeout=5m

log "  -> [2/4] LLM Gateway (Envoy AI Gateway)..."
kubectl --context "$KCTX" rollout status deployment/zelkor-platform-ai-gateway --timeout=5m

log "  -> [3/4] Observability (Langfuse)..."
kubectl --context "$KCTX" rollout status deployment/zelkor-platform-langfuse --timeout=5m

log "  -> [4/4] Agent Orchestrator (Aegra)..."
kubectl --context "$KCTX" rollout status deployment/zelkor-platform-aegra --timeout=5m

if [[ "$INSTALL_EXAMPLES" == "true" && -d "$FINSERVE_CHART_PATH" ]]; then
  log "Applying FinServe demo chart from $FINSERVE_CHART_PATH..."
  helm upgrade --install finserve "$FINSERVE_CHART_PATH" \
    --kube-context "$KCTX" \
    -f "$FINSERVE_VALUES_FILE"

  log "Tracking FinServe demo rollout..."
  log "  -> [1/3] Seeding demo portfolio database..."
  kubectl --context "$KCTX" wait --for=condition=complete job -l app.kubernetes.io/instance=finserve --timeout=3m || true
  log "  -> [2/3] Sandboxed CodeExecutor on gVisor..."
  kubectl --context "$KCTX" rollout status deployment/finserve-code-executor --timeout=5m
  log "  -> [3/3] FinServe Wealth Management Agent..."
  kubectl --context "$KCTX" rollout status deployment/finserve-agent --timeout=5m
fi

log "Done. Zelkor Platform and components are deployed and healthy on kind cluster: $CLUSTER_NAME"

cat <<EOF

======================================================================
  Zelkor Platform — Available Web UIs & Endpoints
======================================================================

  Component               Service                     URL
  ----------------------  --------------------------  ---------------------------------
  Langfuse UI             zelkor-platform-langfuse    http://langfuse.localhost:8088
  Envoy AI Gateway        zelkor-platform-ai-gateway  http://ai-gateway.localhost:8088
  Aegra Agent Runtime     zelkor-platform-aegra       http://aegra.localhost:8088/docs
  FinServe Demo Agent     finserve-agent              http://finserve.localhost:8088/docs

  (Direct Ingress access on host port 8088)
======================================================================
EOF
