#!/usr/bin/env bash
# Zelkor Platform — local bootstrap (Base Tier)
# Deploys a production-like kind cluster with the unified Helm chart and examples.
#
# Usage:
#   ./install.sh
#
# Prerequisites: docker, kind, helm, kubectl

set -euo pipefail

START_TIME=$(date +%s)

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
  docker exec "${CLUSTER_NAME}-control-plane" sh -c "curl -fsSL https://storage.googleapis.com/gvisor/releases/release/latest/x86_64/runsc -o /usr/local/bin/runsc && curl -fsSL https://storage.googleapis.com/gvisor/releases/release/latest/x86_64/containerd-shim-runsc-v1 -o /usr/local/bin/containerd-shim-runsc-v1 && chmod a+rx /usr/local/bin/runsc /usr/local/bin/containerd-shim-runsc-v1" || true
else
  log "Kind cluster already exists: $CLUSTER_NAME"
  kind export kubeconfig --name "$CLUSTER_NAME"
fi

kubectl cluster-info --context "kind-${CLUSTER_NAME}" >/dev/null

if [[ ! -f "$VALUES_FILE" ]]; then
  die "Values file not found: $VALUES_FILE"
fi

KCTX="kind-${CLUSTER_NAME}"

# Ensure Envoy Gateway & Gateway API CRDs are deployed
log "Deploying Envoy Gateway & Gateway API CRDs..."
kubectl apply --context "$KCTX" --server-side -f https://github.com/envoyproxy/gateway/releases/download/v1.9.0/install.yaml

log "Waiting for Envoy Gateway controller readiness..."
kubectl --context "$KCTX" rollout status deployment/envoy-gateway -n envoy-gateway-system --timeout=5m

log "Applying Platform Helm chart from $CHART_PATH..."
HELM_EXTRA_ARGS=()
if [[ -n "${OPENAI_API_KEY:-}" ]]; then
  HELM_EXTRA_ARGS+=(--set "aiGateway.providers.openai.apiKey=${OPENAI_API_KEY}")
fi
if [[ -n "${ANTHROPIC_API_KEY:-}" ]]; then
  HELM_EXTRA_ARGS+=(--set "aiGateway.providers.anthropic.apiKey=${ANTHROPIC_API_KEY}")
fi
if [[ -n "${GEMINI_API_KEY:-}" ]]; then
  HELM_EXTRA_ARGS+=(--set "aiGateway.providers.gemini.apiKey=${GEMINI_API_KEY}")
fi
if [[ -n "${OLLAMA_API_KEY:-}" ]]; then
  HELM_EXTRA_ARGS+=(--set "aiGateway.providers.ollama.apiKey=${OLLAMA_API_KEY}")
fi
if [[ -n "${OLLAMA_HOST:-}" ]]; then
  HELM_EXTRA_ARGS+=(--set "aiGateway.providers.ollama.host=${OLLAMA_HOST}")
fi
if [[ -n "${AZURE_OPENAI_API_KEY:-}" ]]; then
  HELM_EXTRA_ARGS+=(--set "aiGateway.providers.azure.apiKey=${AZURE_OPENAI_API_KEY}")
fi
if [[ -n "${AZURE_OPENAI_ENDPOINT:-}" ]]; then
  HELM_EXTRA_ARGS+=(--set "aiGateway.providers.azure.endpoint=${AZURE_OPENAI_ENDPOINT}")
fi
if [[ -n "${AWS_REGION:-}" ]]; then
  HELM_EXTRA_ARGS+=(--set "aiGateway.providers.bedrock.region=${AWS_REGION}")
fi
if [[ -n "${AWS_ACCESS_KEY_ID:-}" ]]; then
  HELM_EXTRA_ARGS+=(--set "aiGateway.providers.bedrock.accessKeyId=${AWS_ACCESS_KEY_ID}")
fi
if [[ -n "${AWS_SECRET_ACCESS_KEY:-}" ]]; then
  HELM_EXTRA_ARGS+=(--set "aiGateway.providers.bedrock.secretAccessKey=${AWS_SECRET_ACCESS_KEY}")
fi
if [[ -n "${VLLM_BACKEND_URL:-}" ]]; then
  HELM_EXTRA_ARGS+=(--set "aiGateway.providers.vllm.backendUrl=${VLLM_BACKEND_URL}")
fi

if [[ ${#HELM_EXTRA_ARGS[@]} -gt 0 ]]; then
  helm upgrade --install zelkor-platform "$CHART_PATH" \
    --kube-context "$KCTX" \
    -f "$VALUES_FILE" \
    "${HELM_EXTRA_ARGS[@]}"
else
  helm upgrade --install zelkor-platform "$CHART_PATH" \
    --kube-context "$KCTX" \
    -f "$VALUES_FILE"
fi

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

END_TIME=$(date +%s)
TOTAL_DURATION=$((END_TIME - START_TIME))
MINUTES=$((TOTAL_DURATION / 60))
SECONDS=$((TOTAL_DURATION % 60))

log "Done. Zelkor Platform and components are deployed and healthy on kind cluster: $CLUSTER_NAME (installation took ${MINUTES}m ${SECONDS}s / ${TOTAL_DURATION}s)"

cat <<EOF

======================================================================
  Zelkor Platform — Available Web UIs & Endpoints
======================================================================

  Component               Service                     URL
  ----------------------  --------------------------  ---------------------------------
  Langfuse Observability  zelkor-platform-langfuse    http://langfuse.localhost:8088
  Envoy AI Gateway        zelkor-platform-ai-gateway  http://ai-gateway.localhost:8088
  Aegra Agent Runtime     zelkor-platform-aegra       http://aegra.localhost:8088/docs
  FinServe Demo Agent     finserve-agent              http://finserve.localhost:8088/docs

  (Kubernetes Gateway API / Envoy Gateway routed on host port 8088)

======================================================================
  Local Dev Access Credentials & Tokens
======================================================================

  [Langfuse UI & API]
    URL:              http://langfuse.localhost:8088
    User / Password:  admin@zelkor.local / zelkor-dev-password
    Organization:     Zelkor Dev (zelkor-dev)
    Project:          FinServe AI (finserve)
    Public API Key:   pk-lf-zelkor-dev-00000000000000000000
    Secret API Key:   sk-lf-zelkor-dev-00000000000000000000

  [Envoy AI Gateway]
    URL:              http://ai-gateway.localhost:8088/v1/chat/completions
    Bearer Token:     dev-key (or zelkor-community-key)
    Tenant Header:    X-Tenant-ID: Bank_Alpha

  [FinServe Demo Agent]
    URL:              http://finserve.localhost:8088/runs/stream
    Bearer Tokens:    Authorization: Bearer dev:Bank_Alpha
                      Authorization: Bearer dev:Bank_Beta

  [Aegra Agent Runtime]
    URL:              http://aegra.localhost:8088
    Bearer Token:     Authorization: Bearer dev-key

  [Databases (Internal Cluster / Port-Forward)]
    PostgreSQL:       postgresql://zelkor:zelkor-dev-password@localhost:5432/finserve
    Valkey (Redis):   localhost:6379
    ClickHouse:       http://localhost:8123 (user: default)
    Qdrant:           http://localhost:6333

======================================================================
  Quick Test Commands (Instant Live Tracing)
======================================================================

  1. Test Envoy AI Gateway:
     curl -X POST http://ai-gateway.localhost:8088/v1/chat/completions \\
       -H "Content-Type: application/json" \\
       -H "Authorization: Bearer dev-key" \\
       -H "X-Tenant-ID: Bank_Alpha" \\
       -d '{"model":"openai/gpt-4o-mini","messages":[{"role":"user","content":"Hello from Zelkor!"}]}'

  2. Test FinServe Agent Stream:
     curl -X POST http://finserve.localhost:8088/runs/stream \\
       -H "Content-Type: application/json" \\
       -H "Authorization: Bearer dev:Bank_Alpha" \\
       -d '{"assistant_id":"finserve_agent","input":{"messages":[{"role":"user","content":"What is my portfolio valuation?"}]}}'

  3. View Traces:
     Open http://langfuse.localhost:8088 -> Log in -> Project: FinServe AI -> Traces

======================================================================
  Total Installation Time: ${MINUTES}m ${SECONDS}s (${TOTAL_DURATION} seconds)
======================================================================
EOF
