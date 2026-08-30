#!/usr/bin/env bash
# Zelkor Platform — local bootstrap (Base Tier)
# Deploys a production-like kind cluster with the unified Helm chart and examples.
#
# Usage:
#   OPENAI_API_KEY=sk-... ./install.sh
#   OLLAMA_API_KEY=... ./install.sh
#   OLLAMA_LOCAL_HOST=http://host.docker.internal:11434 ./install.sh
#
# Prerequisites: docker, kind, helm, kubectl, and at least one LLM provider (see below)

set -euo pipefail

START_TIME=$(date +%s)

CLUSTER_NAME="${CLUSTER_NAME:-zelkor}"
CHART_PATH="${CHART_PATH:-charts/zelkor-platform}"
VALUES_FILE="${VALUES_FILE:-profiles/values-local.yaml}"
KIND_CONFIG="${KIND_CONFIG:-kind-config.yaml}"
INSTALL_EXAMPLES="${INSTALL_EXAMPLES:-true}"
FINSERVE_CHART_PATH="${FINSERVE_CHART_PATH:-examples/finserve/chart}"
FINSERVE_VALUES_FILE="${FINSERVE_VALUES_FILE:-${FINSERVE_CHART_PATH}/values-local.yaml}"
FINSERVE_PLATFORM_OVERLAY="${FINSERVE_PLATFORM_OVERLAY:-${FINSERVE_CHART_PATH}/values-platform-overlay.yaml}"
BUILD_IMAGES="${BUILD_IMAGES:-false}"
KIND_LOAD_IMAGES="${KIND_LOAD_IMAGES:-false}"
IMAGE_REGISTRY="${IMAGE_REGISTRY:-ghcr.io/devopssquaddev}"
IMAGE_TAG="${IMAGE_TAG:-dev}"
# Pinned gVisor point release for kind sandbox bootstrap (see internal/plan/component_compatibility_matrix.md)
GVISOR_RELEASE="${GVISOR_RELEASE:-20260601}"

log() { echo "[install] $*"; }
die() { echo "[install] ERROR: $*" >&2; exit 1; }

LLM_PROVIDER_COUNT=0
LLM_PROVIDER_SUMMARY=""
SELECTED_OLLAMA_LOCAL_HOST=""

register_llm_provider() {
  local name="$1"
  LLM_PROVIDER_COUNT=$((LLM_PROVIDER_COUNT + 1))
  if [[ -n "$LLM_PROVIDER_SUMMARY" ]]; then
    LLM_PROVIDER_SUMMARY+=", "
  fi
  LLM_PROVIDER_SUMMARY+="$name"
}

resolve_llm_provider_prerequisites() {
  if [[ -n "${AZURE_OPENAI_API_KEY:-}" || -n "${AZURE_OPENAI_ENDPOINT:-}" ]]; then
    die "Azure OpenAI env vars are not supported in the CE gateway chart yet. Use OPENAI_API_KEY, OLLAMA_API_KEY, or OLLAMA_LOCAL_HOST."
  fi
  if [[ -n "${AWS_REGION:-}" || -n "${AWS_ACCESS_KEY_ID:-}" || -n "${AWS_SECRET_ACCESS_KEY:-}" ]]; then
    die "AWS Bedrock env vars are not supported in the CE gateway chart yet. Use OPENAI_API_KEY, OLLAMA_API_KEY, or OLLAMA_LOCAL_HOST."
  fi

  if [[ -n "${OPENAI_API_KEY:-}" ]]; then register_llm_provider "OpenAI"; fi
  if [[ -n "${ANTHROPIC_API_KEY:-}" ]]; then register_llm_provider "Anthropic"; fi
  if [[ -n "${GEMINI_API_KEY:-}" ]]; then register_llm_provider "Gemini"; fi
  if [[ -n "${OLLAMA_API_KEY:-}" ]]; then register_llm_provider "Ollama Cloud"; fi
  if [[ -n "${VLLM_BACKEND_URL:-}" ]]; then register_llm_provider "vLLM"; fi

  if [[ -n "${OLLAMA_LOCAL_HOST:-}" ]]; then
    SELECTED_OLLAMA_LOCAL_HOST="$OLLAMA_LOCAL_HOST"
    register_llm_provider "Ollama Local"
  elif [[ -n "${OLLAMA_HOST:-}" && "${OLLAMA_HOST}" != "https://ollama.com" ]]; then
    SELECTED_OLLAMA_LOCAL_HOST="$OLLAMA_HOST"
    register_llm_provider "Ollama Local"
  fi

  if [[ "$LLM_PROVIDER_COUNT" -eq 0 ]]; then
    cat >&2 <<'EOF'
[install] ERROR: Choose at least one LLM provider before install.

  OpenAI (chat + embeddings):
    OPENAI_API_KEY=sk-... ./install.sh

  Ollama Cloud:
    OLLAMA_API_KEY=... ./install.sh

  Ollama Local (host Ollama — run `ollama serve` first):
    OLLAMA_LOCAL_HOST=http://host.docker.internal:11434 ./install.sh

  Anthropic / Gemini / vLLM:
    ANTHROPIC_API_KEY=... ./install.sh
    GEMINI_API_KEY=... ./install.sh
    VLLM_BACKEND_URL=http://host:8000/v1 ./install.sh

Clients use Bearer dev-key; upstream keys stay in the gateway secret (two-tier auth).
EOF
    exit 1
  fi

  if [[ -z "${DEFAULT_LLM_MODEL:-}" ]]; then
    if [[ -n "${OPENAI_API_KEY:-}" ]]; then
      DEFAULT_LLM_MODEL="openai/gpt-4o-mini"
    elif [[ -n "${OLLAMA_API_KEY:-}" ]]; then
      DEFAULT_LLM_MODEL="gpt-oss:20b"
    elif [[ -n "$SELECTED_OLLAMA_LOCAL_HOST" ]]; then
      DEFAULT_LLM_MODEL="ollama/llama3.2"
    elif [[ -n "${ANTHROPIC_API_KEY:-}" ]]; then
      DEFAULT_LLM_MODEL="anthropic/claude-3-5-sonnet"
    elif [[ -n "${GEMINI_API_KEY:-}" ]]; then
      DEFAULT_LLM_MODEL="gemini/gemini-2.0-flash"
    elif [[ -n "${VLLM_BACKEND_URL:-}" ]]; then
      DEFAULT_LLM_MODEL="vllm/default"
    fi
  fi
  export DEFAULT_LLM_MODEL
  log "LLM providers: ${LLM_PROVIDER_SUMMARY} (DEFAULT_LLM_MODEL=${DEFAULT_LLM_MODEL})"
}

patch_kind_host_docker_internal() {
  local node="${CLUSTER_NAME}-control-plane"
  local gateway_ip="172.17.0.1"
  if gateway_ip_detected="$(docker network inspect kind -f '{{(index .IPAM.Config 0).Gateway}}' 2>/dev/null)"; then
    if [[ -n "$gateway_ip_detected" && "$gateway_ip_detected" != "<no value>" ]]; then
      gateway_ip="$gateway_ip_detected"
    fi
  fi
  log "Patching kind node /etc/hosts: ${gateway_ip} host.docker.internal"
  docker exec "$node" sh -c "grep -q 'host.docker.internal' /etc/hosts || echo '${gateway_ip} host.docker.internal' >> /etc/hosts"
}

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

resolve_llm_provider_prerequisites

if ! kind get clusters 2>/dev/null | grep -qx "$CLUSTER_NAME"; then
  log "Creating kind cluster: $CLUSTER_NAME"
  if [[ -f "$KIND_CONFIG" ]]; then
    kind create cluster --name "$CLUSTER_NAME" --config "$KIND_CONFIG"
  else
    kind create cluster --name "$CLUSTER_NAME"
  fi

  # Install runsc (gVisor) binary on kind control plane node (pinned release, not release/latest)
  log "Configuring gVisor (runsc) release ${GVISOR_RELEASE} on kind node..."
  docker exec "${CLUSTER_NAME}-control-plane" sh -c "
    set -e
    ARCH=\$(uname -m)
    BASE=https://storage.googleapis.com/gvisor/releases/release/${GVISOR_RELEASE}/\${ARCH}
    curl -fsSL \"\${BASE}/runsc\" -o /usr/local/bin/runsc
    curl -fsSL \"\${BASE}/containerd-shim-runsc-v1\" -o /usr/local/bin/containerd-shim-runsc-v1
    chmod a+rx /usr/local/bin/runsc /usr/local/bin/containerd-shim-runsc-v1
  " || log "WARNING: gVisor install failed (sandbox RuntimeClass may not work on this node)"

  if [[ -n "$SELECTED_OLLAMA_LOCAL_HOST" && "$SELECTED_OLLAMA_LOCAL_HOST" == *"host.docker.internal"* ]]; then
    patch_kind_host_docker_internal
  fi
else
  log "Kind cluster already exists: $CLUSTER_NAME"
  kind export kubeconfig --name "$CLUSTER_NAME"
fi

kubectl cluster-info --context "kind-${CLUSTER_NAME}" >/dev/null

if [[ "$BUILD_IMAGES" == "true" ]]; then
  log "Building first-party images (tag ${IMAGE_TAG})..."
  IMAGE_REGISTRY="$IMAGE_REGISTRY" IMAGE_TAG="$IMAGE_TAG" ./scripts/build-images.sh
  KIND_LOAD_IMAGES=true
fi

if [[ "$KIND_LOAD_IMAGES" == "true" ]]; then
  log "Loading first-party images into kind cluster ${CLUSTER_NAME}..."
  IMAGE_REGISTRY="$IMAGE_REGISTRY" IMAGE_TAG="$IMAGE_TAG" KIND_CLUSTER="$CLUSTER_NAME" \
    ./scripts/build-images.sh --load-only --kind-load
fi

if [[ ! -f "$VALUES_FILE" ]]; then
  die "Values file not found: $VALUES_FILE"
fi

KCTX="kind-${CLUSTER_NAME}"

# Ensure Envoy Gateway & Gateway API CRDs are deployed
log "Deploying Envoy Gateway & Gateway API CRDs..."
kubectl apply --context "$KCTX" --server-side -f https://github.com/envoyproxy/gateway/releases/download/v1.9.0/install.yaml

# Enable Backend extension API in Envoy Gateway config
log "Enabling Backend extension API in Envoy Gateway config..."
kubectl --context "$KCTX" apply -f - <<'EOF'
apiVersion: v1
kind: ConfigMap
metadata:
  name: envoy-gateway-config
  namespace: envoy-gateway-system
data:
  envoy-gateway.yaml: |
    apiVersion: gateway.envoyproxy.io/v1alpha1
    kind: EnvoyGateway
    extensionApis:
      enableBackend: true
      enableEnvoyPatchPolicy: true
    extensionManager:
      hooks:
        xdsTranslator:
          translation:
            listener:
              includeAll: true
            route:
              includeAll: true
            cluster:
              includeAll: true
            secret:
              includeAll: true
          post:
            - Translation
            - Cluster
            - Route
      service:
        fqdn:
          hostname: ai-gateway-controller.envoy-ai-gateway-system.svc.cluster.local
          port: 1063
    gateway:
      controllerName: gateway.envoyproxy.io/gatewayclass-controller
    logging:
      level:
        default: info
    provider:
      kubernetes:
        rateLimitDeployment:
          container:
            image: docker.io/envoyproxy/ratelimit:17b1956c
          patch:
            type: StrategicMerge
            value:
              spec:
                template:
                  spec:
                    containers:
                    - imagePullPolicy: IfNotPresent
                      name: envoy-ratelimit
        shutdownManager:
          image: envoyproxy/gateway:v1.9.0
      type: Kubernetes
EOF
kubectl --context "$KCTX" rollout restart deployment/envoy-gateway -n envoy-gateway-system

log "Waiting for Envoy Gateway controller readiness..."
kubectl --context "$KCTX" rollout status deployment/envoy-gateway -n envoy-gateway-system --timeout=5m

# Ensure Envoy AI Gateway CRDs & Controller are deployed
log "Deploying Envoy AI Gateway CRDs & Controller..."
helm upgrade -i aieg-crd oci://docker.io/envoyproxy/ai-gateway-crds-helm \
  --kube-context "$KCTX" \
  --version v1.1.0 \
  --namespace envoy-ai-gateway-system \
  --create-namespace

helm upgrade -i aieg oci://docker.io/envoyproxy/ai-gateway-helm \
  --kube-context "$KCTX" \
  --version v1.1.0 \
  --namespace envoy-ai-gateway-system \
  --create-namespace

log "Waiting for Envoy AI Gateway controller readiness..."
kubectl --context "$KCTX" rollout status deployment/ai-gateway-controller -n envoy-ai-gateway-system --timeout=5m

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
  HELM_EXTRA_ARGS+=(--set "aiGateway.providers.ollamaCloud.apiKey=${OLLAMA_API_KEY}")
fi
if [[ -n "${OLLAMA_LOCAL_HOST:-}" ]]; then
  HELM_EXTRA_ARGS+=(--set "aiGateway.providers.ollamaLocal.host=${OLLAMA_LOCAL_HOST}")
elif [[ -n "$SELECTED_OLLAMA_LOCAL_HOST" ]]; then
  HELM_EXTRA_ARGS+=(--set "aiGateway.providers.ollamaLocal.host=${SELECTED_OLLAMA_LOCAL_HOST}")
fi
if [[ -n "${VLLM_BACKEND_URL:-}" ]]; then
  HELM_EXTRA_ARGS+=(--set "aiGateway.providers.vllm.backendUrl=${VLLM_BACKEND_URL}")
fi
if [[ -n "${DEFAULT_LLM_MODEL:-}" ]]; then
  HELM_EXTRA_ARGS+=(--set "guardrails.nemo.model=${DEFAULT_LLM_MODEL}")
fi

if [[ "$INSTALL_EXAMPLES" == "true" && -f "$FINSERVE_PLATFORM_OVERLAY" ]]; then
  HELM_EXTRA_ARGS+=(-f "$FINSERVE_PLATFORM_OVERLAY")
  log "Platform overlay: $FINSERVE_PLATFORM_OVERLAY"
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
log "  -> [1/5] Databases (PostgreSQL, Valkey, ClickHouse, Qdrant, SeaweedFS)..."
kubectl --context "$KCTX" rollout status statefulset/zelkor-platform-postgresql --timeout=5m
kubectl --context "$KCTX" rollout status deployment/zelkor-platform-valkey --timeout=5m
kubectl --context "$KCTX" rollout status statefulset/zelkor-platform-clickhouse --timeout=5m
kubectl --context "$KCTX" rollout status statefulset/zelkor-platform-qdrant --timeout=5m
kubectl --context "$KCTX" rollout status deployment/zelkor-platform-seaweedfs --timeout=5m

log "  -> [2/5] LLM Gateway (Envoy AI Gateway)..."
kubectl --context "$KCTX" rollout status deployment/ai-gateway-controller -n envoy-ai-gateway-system --timeout=5m

discover_internal_gateway_url() {
  local svc=""
  for _ in $(seq 1 30); do
    svc=$(kubectl --context "$KCTX" get svc -n envoy-gateway-system -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}' 2>/dev/null | grep '^envoy-default-.*gateway-' | head -1 || true)
    if [[ -n "$svc" ]]; then
      echo "http://${svc}.envoy-gateway-system.svc.cluster.local:80/v1"
      return 0
    fi
    sleep 2
  done
  return 1
}

if GATEWAY_INTERNAL_URL=$(discover_internal_gateway_url); then
  GATEWAY_TARGET_HOST="${GATEWAY_INTERNAL_URL#http://}"
  GATEWAY_TARGET_HOST="${GATEWAY_TARGET_HOST%%/*}"
  GATEWAY_TARGET_HOST="${GATEWAY_TARGET_HOST%%:*}"
  log "Patching in-cluster AI Gateway URL for platform workloads: ${GATEWAY_INTERNAL_URL}"
  helm upgrade zelkor-platform "$CHART_PATH" \
    --kube-context "$KCTX" \
    -f "$VALUES_FILE" \
    --reuse-values \
    --set "aiGateway.internalUrl=${GATEWAY_INTERNAL_URL}" \
    --set "aiGateway.inClusterService.targetHost=${GATEWAY_TARGET_HOST}" \
    --set "mcp.qdrantMCP.aiGatewayUrl=${GATEWAY_INTERNAL_URL}" \
    "${HELM_EXTRA_ARGS[@]}"
else
  log "WARNING: Envoy data-plane Service not found; NeMo/MCP in-cluster LLM calls may fail until aiGateway.internalUrl is set."
fi

log "  -> [3/5] Observability (Langfuse web + worker)..."
kubectl --context "$KCTX" rollout status deployment/zelkor-platform-langfuse --timeout=5m
kubectl --context "$KCTX" rollout status deployment/zelkor-platform-langfuse-worker --timeout=5m

log "  -> [4/5] Agent Orchestrator (Aegra)..."
kubectl --context "$KCTX" rollout status deployment/zelkor-platform-aegra --timeout=5m

if kubectl --context "$KCTX" get deployment/zelkor-platform-nemo >/dev/null 2>&1; then
  log "  -> Guardrails (NeMo CPU)..."
  kubectl --context "$KCTX" rollout status deployment/zelkor-platform-nemo --timeout=5m
fi

if kubectl --context "$KCTX" get deployment/zelkor-platform-mcp-gateway >/dev/null 2>&1; then
  log "  -> Native MCP Servers (gateway, postgres, qdrant, sandbox)..."
  kubectl --context "$KCTX" rollout status deployment/zelkor-platform-mcp-gateway --timeout=5m
  kubectl --context "$KCTX" rollout status deployment/zelkor-platform-mcp-postgres --timeout=5m
  kubectl --context "$KCTX" rollout status deployment/zelkor-platform-mcp-qdrant --timeout=5m
  kubectl --context "$KCTX" rollout status deployment/zelkor-platform-mcp-sandbox --timeout=5m
  for i in 0 1 2; do
    if kubectl --context "$KCTX" get deployment/zelkor-platform-mcp-sandbox-worker-$i >/dev/null 2>&1; then
      kubectl --context "$KCTX" rollout status deployment/zelkor-platform-mcp-sandbox-worker-$i --timeout=5m
    fi
  done
fi

if [[ "$INSTALL_EXAMPLES" == "true" && -d "$FINSERVE_CHART_PATH" ]]; then
  log "Applying FinServe demo chart from $FINSERVE_CHART_PATH..."
  helm dependency update "$FINSERVE_CHART_PATH" >/dev/null
  FINSERVE_HELM_ARGS=()
  if [[ -n "${DEFAULT_LLM_MODEL:-}" ]]; then
    FINSERVE_HELM_ARGS+=(--set-string "zelkor-agent.platform.defaultLlmModel=${DEFAULT_LLM_MODEL}")
  fi
  helm upgrade --install finserve "$FINSERVE_CHART_PATH" \
    --kube-context "$KCTX" \
    -f "$FINSERVE_VALUES_FILE" \
    "${FINSERVE_HELM_ARGS[@]}"

  log "Tracking FinServe demo rollout..."
  log "  -> [1/2] Seeding demo portfolio database..."
  kubectl --context "$KCTX" wait --for=condition=complete job -l app.kubernetes.io/instance=finserve --timeout=3m || true
  log "  -> [2/2] FinServe ClusterIP worker (graph_id=finserve)..."
  kubectl --context "$KCTX" rollout status deployment/finserve-agent --timeout=5m
fi

END_TIME=$(date +%s)
TOTAL_DURATION=$((END_TIME - START_TIME))
MINUTES=$((TOTAL_DURATION / 60))
SECONDS=$((TOTAL_DURATION % 60))

log "Done. Zelkor Platform and components are deployed and healthy on kind cluster: $CLUSTER_NAME (installation took ${MINUTES}m ${SECONDS}s / ${TOTAL_DURATION}s)"

{
cat <<EOF

======================================================================
  Zelkor Platform — Available Web UIs & Endpoints
======================================================================

  Component               Service                     URL
  ----------------------  --------------------------  ---------------------------------
  Langfuse Observability  zelkor-platform-langfuse    http://langfuse.localhost:8088
  Envoy AI Gateway        ai-gateway-controller       http://ai-gateway.localhost:8088
  Aegra Agent Runtime     zelkor-platform-aegra       http://aegra.localhost:8088/docs
EOF
if [[ "$INSTALL_EXAMPLES" == "true" ]]; then
cat <<EOF
  FinServe Demo (front door) zelkor-platform-aegra    http://aegra.localhost:8088  graph_id=finserve
EOF
fi
cat <<EOF
  Native MCP Gateway      zelkor-platform-mcp-gateway http://mcp.localhost:8088/mcp
  NeMo Guardrails (CPU)   zelkor-platform-nemo        http://nemo.localhost:8088/v1/rails/configs

  (Kubernetes Gateway API / Envoy Gateway routed on host port 8088)

======================================================================
  Local Dev Access Credentials & Tokens
======================================================================

  [Langfuse UI & API]
    URL:              http://langfuse.localhost:8088
    User / Password:  admin@zelkor.local / zelkor-dev-password
    Organization:     Zelkor Dev (zelkor-dev)
    Project:          Zelkor Platform (zelkor-platform)
    Public API Key:   pk-lf-zelkor-dev-00000000000000000000
    Secret API Key:   sk-lf-zelkor-dev-00000000000000000000

  [Envoy AI Gateway]
    URL:              http://ai-gateway.localhost:8088/v1/chat/completions
    Bearer Token:     dev-key (or zelkor-community-key)
    Tenant Header:    X-Tenant-ID: tenant_a
    LLM Providers:    ${LLM_PROVIDER_SUMMARY}
    Default Model:    ${DEFAULT_LLM_MODEL}
EOF
if [[ "$INSTALL_EXAMPLES" == "true" ]]; then
cat <<EOF

  [FinServe Demo Agent]
    URL:              http://aegra.localhost:8088  (platform Aegra, graph_id=finserve)
    Bearer Tokens:    Authorization: Bearer dev:Bank_Alpha
                      Authorization: Bearer dev:Bank_Beta
EOF
fi
cat <<EOF

  [Aegra Agent Runtime]
    URL:              http://aegra.localhost:8088
    Bearer Token:     Authorization: Bearer dev:tenant_a

  [Databases (Internal Cluster / Port-Forward)]
    PostgreSQL:       postgresql://zelkor:zelkor-dev-password@localhost:5432/zelkor
    Valkey (Redis):   localhost:6379
    ClickHouse:       http://localhost:8123 (user: default)
    Qdrant:           http://localhost:6333

======================================================================
  Quick Test Commands (Instant Live Tracing)
======================================================================

  1. Test Envoy AI Gateway (model must match your install provider):
     curl -X POST http://ai-gateway.localhost:8088/v1/chat/completions \\
       -H "Content-Type: application/json" \\
       -H "Authorization: Bearer dev-key" \\
       -H "X-Tenant-ID: tenant_a" \\
       -d '{"model":"${DEFAULT_LLM_MODEL}","messages":[{"role":"user","content":"Hello from Zelkor!"}]}'
EOF
if [[ "$INSTALL_EXAMPLES" == "true" ]]; then
cat <<EOF

  2. Test FinServe via platform Aegra (graph_id=finserve):
     curl -X POST http://aegra.localhost:8088/threads \\
       -H "Content-Type: application/json" \\
       -H "Authorization: Bearer dev:Bank_Alpha" \\
       -d '{"if_exists":"do_nothing"}'
     curl -X POST http://aegra.localhost:8088/runs/wait \\
       -H "Content-Type: application/json" \\
       -H "Authorization: Bearer dev:Bank_Alpha" \\
       -H "X-Graph-ID: finserve" \\
       -d '{"graph_id":"finserve","input":{"messages":[{"role":"human","content":"What is my portfolio valuation?"}]}}'
EOF
fi
cat <<EOF

  3. View Traces:
     Open http://langfuse.localhost:8088 -> Log in -> Project: Zelkor Platform -> Traces

======================================================================
  Total Installation Time: ${MINUTES}m ${SECONDS}s (${TOTAL_DURATION} seconds)
======================================================================
EOF
}
