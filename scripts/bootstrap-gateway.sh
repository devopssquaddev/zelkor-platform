#!/usr/bin/env bash
# Idempotent Envoy Gateway + Envoy AI Gateway bootstrap for customer Kubernetes.
# Also used by ./install.sh (kind). Skip controllers when already healthy or --skip-* is set.
# Does not patch envoy-gateway-config on a pre-existing EG unless --patch-extension-manager
# or Zelkor already owns that install.
set -euo pipefail

ZELKOR_REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=lib/bootstrap-ownership.sh
source "${ZELKOR_REPO_ROOT}/scripts/lib/bootstrap-ownership.sh"
# shellcheck source=lib/gateway-policies.sh
source "${ZELKOR_REPO_ROOT}/scripts/lib/gateway-policies.sh"

ENVOY_GATEWAY_VERSION="${ENVOY_GATEWAY_VERSION:-v1.9.1}"
AI_GATEWAY_HELM_VERSION="${AI_GATEWAY_HELM_VERSION:-v1.1.0}"
ROLLOUT_WAIT_TIMEOUT="${ROLLOUT_WAIT_TIMEOUT:-5m}"
HELM_INSTALL_TIMEOUT="${HELM_INSTALL_TIMEOUT:-15m}"

SKIP_ENVOY_GATEWAY=0
SKIP_AI_GATEWAY=0
PATCH_EXTENSION_MANAGER=0
KUBECONFIG_FILE=""
KUBE_CONTEXT=""
KUBECTL_ARGS=()
HELM_ARGS=()

usage() {
  cat <<'EOF'
Usage: ./scripts/bootstrap-gateway.sh [OPTIONS]

Installs Envoy Gateway and Envoy AI Gateway when missing. Idempotent.

Options:
  --skip-envoy-gateway         Skip EG install and ConfigMap patch (shared-gateway tenant)
  --skip-ai-gateway            Skip AI Gateway Helm install
  --patch-extension-manager    Explicitly replace envoy-gateway-config (restarts EG; cluster-wide)
  --kubeconfig PATH            kubectl / helm kubeconfig
  --kube-context NAME          kubectl context / helm kube-context
  -h, --help                   Show this help

Examples:
  # Greenfield or layered routing (install both)
  ./scripts/bootstrap-gateway.sh

  # EG exists; add AI Gateway extension
  ./scripts/bootstrap-gateway.sh --skip-envoy-gateway --patch-extension-manager

  # Both already installed (Zelkor tenant only)
  ./scripts/bootstrap-gateway.sh --skip-envoy-gateway --skip-ai-gateway
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --kubeconfig)
      [[ $# -ge 2 ]] || { echo "missing value for --kubeconfig" >&2; exit 2; }
      KUBECONFIG_FILE="$2"
      shift
      ;;
    --kube-context)
      [[ $# -ge 2 ]] || { echo "missing value for --kube-context" >&2; exit 2; }
      KUBE_CONTEXT="$2"
      shift
      ;;
    --skip-envoy-gateway) SKIP_ENVOY_GATEWAY=1 ;;
    --skip-ai-gateway) SKIP_AI_GATEWAY=1 ;;
    --patch-extension-manager) PATCH_EXTENSION_MANAGER=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown flag: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

need() {
  command -v "$1" >/dev/null 2>&1 || { echo "missing required command: $1" >&2; exit 1; }
}
need kubectl
need helm

if [[ -n "$KUBECONFIG_FILE" ]]; then
  KUBECTL_ARGS+=(--kubeconfig "$KUBECONFIG_FILE")
  HELM_ARGS+=(--kubeconfig "$KUBECONFIG_FILE")
fi
if [[ -n "$KUBE_CONTEXT" ]]; then
  KUBECTL_ARGS+=(--context "$KUBE_CONTEXT")
  HELM_ARGS+=(--kube-context "$KUBE_CONTEXT")
fi

deployment_available() {
  local ns="$1"
  local name="$2"
  local available
  available=$(kubectl "${KUBECTL_ARGS[@]}" get deployment "$name" -n "$ns" \
    -o jsonpath='{.status.conditions[?(@.type=="Available")].status}' 2>/dev/null || true)
  [[ "$available" == "True" ]]
}

wait_rollout() {
  local ns="$1"
  local name="$2"
  kubectl "${KUBECTL_ARGS[@]}" rollout status "deployment/${name}" -n "$ns" --timeout="$ROLLOUT_WAIT_TIMEOUT"
}

_install_gateway_policies() {
  local policies_chart="${ZELKOR_REPO_ROOT}/charts/zelkor-gateway-policies"
  if [[ ! -d "${policies_chart}" ]]; then
    echo "  WARN: ${policies_chart} missing — skip zelkor-gateway-policies"
    return 0
  fi
  if [[ "${ZELKOR_SKIP_GATEWAY_POLICIES:-0}" == "1" ]]; then
    echo "skip zelkor-gateway-policies (shared/brownfield)"
    return 0
  fi
  local gw_name gw_ns listeners_json
  gw_name="${ZELKOR_GATEWAY_POLICIES_GATEWAY_NAME:-zelkor-platform-gateway}"
  gw_ns="${ZELKOR_GATEWAY_POLICIES_GATEWAY_NAMESPACE:-default}"
  if [[ -n "${ZELKOR_GATEWAY_POLICIES_LISTENERS_JSON:-}" ]]; then
    listeners_json="$ZELKOR_GATEWAY_POLICIES_LISTENERS_JSON"
  else
    GATEWAY_POLICIES_HELM_SET_SCAN=()
    listeners_json="$(gateway_policies_listeners_json)"
  fi
  local listener_sets=()
  while IFS= read -r line; do
    [[ -n "$line" ]] && listener_sets+=("$line")
  done < <(LISTENERS_JSON="$listeners_json" python3 -c 'import json, os
for i, item in enumerate(json.loads(os.environ["LISTENERS_JSON"])):
    port = item["port"] if isinstance(item, dict) else item
    print(f"--set=listeners[{i}].port={int(port)}")')
  echo "Installing zelkor-gateway-policies (envoy-gateway-system)..."
  helm upgrade --install zelkor-gateway-policies "${policies_chart}" \
    "${HELM_ARGS[@]}" \
    --namespace envoy-gateway-system \
    --create-namespace \
    --set "gateway.name=${gw_name}" \
    --set "gateway.namespace=${gw_ns}" \
    "${listener_sets[@]}" \
    --wait --timeout 3m
}

_aigw_mcp_seed_from_helm() {
  helm "${HELM_ARGS[@]}" get values aieg -n envoy-ai-gateway-system -o json 2>/dev/null \
    | python3 -c 'import json,sys; d=json.load(sys.stdin); print((d.get("mcp") or {}).get("sessionEncryption", {}).get("seed") or "")' \
    2>/dev/null || true
}

_ensure_aigw_mcp_session_seed() {
  if ! deployment_available envoy-ai-gateway-system ai-gateway-controller; then
    return 0
  fi
  local current
  current="$(_aigw_mcp_seed_from_helm)"
  if [[ -n "$current" && "$current" != "default-insecure-seed" ]]; then
    echo "MCP session encryption seed already set on aieg release"
    return 0
  fi
  local seed_file
  seed_file="$(mktemp)"
  trap 'rm -f "$seed_file"' RETURN
  if [[ -n "${ZELKOR_MCP_SESSION_SEED:-}" ]]; then
    printf '%s' "$ZELKOR_MCP_SESSION_SEED" >"$seed_file"
  elif command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32 >"$seed_file"
  else
    head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n' >"$seed_file"
  fi
  echo "Setting MCP session encryption seed on envoy-ai-gateway (aieg) release..."
  helm upgrade aieg oci://docker.io/envoyproxy/ai-gateway-helm \
    "${HELM_ARGS[@]}" \
    --namespace envoy-ai-gateway-system \
    --reuse-values \
    --set-file "mcp.sessionEncryption.seed=${seed_file}" \
    --wait --timeout 5m
}

EG_CM_BODY=$(cat <<'EOF'
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
      image: envoyproxy/gateway:v1.9.1
  type: Kubernetes
rateLimit:
  failClosed: false
  backend:
    type: Redis
    redis:
      url: envoy-ratelimit-redis.envoy-gateway-system.svc:6379
EOF
)

apply_ratelimit_redis() {
  echo "Ensuring Envoy Gateway rate-limit Redis (envoy-ratelimit-redis)..."
  kubectl "${KUBECTL_ARGS[@]}" apply -f - <<'EOF'
apiVersion: v1
kind: Service
metadata:
  name: envoy-ratelimit-redis
  namespace: envoy-gateway-system
  labels:
    app.kubernetes.io/name: envoy-ratelimit-redis
    app.kubernetes.io/part-of: zelkor
spec:
  selector:
    app.kubernetes.io/name: envoy-ratelimit-redis
  ports:
    - name: redis
      port: 6379
      targetPort: 6379
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: envoy-ratelimit-redis
  namespace: envoy-gateway-system
  labels:
    app.kubernetes.io/name: envoy-ratelimit-redis
    app.kubernetes.io/part-of: zelkor
spec:
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: envoy-ratelimit-redis
  template:
    metadata:
      labels:
        app.kubernetes.io/name: envoy-ratelimit-redis
        app.kubernetes.io/part-of: zelkor
    spec:
      containers:
        - name: redis
          image: docker.io/valkey/valkey:7.2.14-alpine
          imagePullPolicy: IfNotPresent
          ports:
            - containerPort: 6379
              name: redis
          resources:
            requests:
              cpu: 25m
              memory: 32Mi
            limits:
              cpu: 200m
              memory: 128Mi
          livenessProbe:
            tcpSocket:
              port: 6379
            initialDelaySeconds: 5
            periodSeconds: 10
          readinessProbe:
            tcpSocket:
              port: 6379
            initialDelaySeconds: 2
            periodSeconds: 5
EOF
  wait_rollout envoy-gateway-system envoy-ratelimit-redis
}

apply_extension_config() {
  apply_ratelimit_redis
  local eg_cm_current
  eg_cm_current=$(kubectl "${KUBECTL_ARGS[@]}" get configmap envoy-gateway-config -n envoy-gateway-system \
    -o jsonpath='{.data.envoy-gateway\.yaml}' 2>/dev/null || true)

  if [[ "${eg_cm_current%$'\n'}" == "${EG_CM_BODY%$'\n'}" ]]; then
    echo "Envoy Gateway extension config unchanged; skipping patch"
    return 0
  fi

  echo "Applying Envoy Gateway AI extension config..."
  kubectl "${KUBECTL_ARGS[@]}" apply -f - <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: envoy-gateway-config
  namespace: envoy-gateway-system
data:
  envoy-gateway.yaml: |
$(printf '%s\n' "$EG_CM_BODY" | sed 's/^/    /')
EOF
  echo "Restarting Envoy Gateway controller..."
  kubectl "${KUBECTL_ARGS[@]}" rollout restart deployment/envoy-gateway -n envoy-gateway-system
  wait_rollout envoy-gateway-system envoy-gateway
}

if [[ "$SKIP_ENVOY_GATEWAY" -eq 0 ]]; then
  eg_ready=0
  if deployment_available envoy-gateway-system envoy-gateway; then
    eg_ready=1
  fi
  eg_owned=0
  if zelkor_ownership_owns envoy-gateway || zelkor_ownership_ns_owned envoy-gateway-system; then
    eg_owned=1
  fi
  eg_action="$(zelkor_eg_patch_action "$eg_ready" "$eg_owned" "$PATCH_EXTENSION_MANAGER" "$SKIP_AI_GATEWAY")"

  if [[ "$eg_ready" -eq 0 ]]; then
    echo "Deploying Envoy Gateway ${ENVOY_GATEWAY_VERSION}..."
    kubectl "${KUBECTL_ARGS[@]}" apply --server-side -f \
      "https://github.com/envoyproxy/gateway/releases/download/${ENVOY_GATEWAY_VERSION}/install.yaml"
    zelkor_ownership_annotate_ns envoy-gateway-system
    zelkor_ownership_record envoy-gateway
    apply_extension_config
  elif [[ "$eg_action" == "apply" ]]; then
    if [[ "$eg_owned" -eq 1 ]]; then
      echo "Envoy Gateway already ready (Zelkor-owned); ensuring extension config"
    else
      echo "WARNING: --patch-extension-manager replaces envoy-gateway-config and restarts Envoy Gateway (cluster ingress)."
    fi
    apply_extension_config
  elif [[ "$eg_action" == "fail" ]]; then
    cat >&2 <<'EOF'
error: Envoy Gateway is already running and was not installed by Zelkor.
Refusing to replace envoy-gateway-config (that restarts EG and can take down cluster ingress).

  Layered (your ingress fronts a Zelkor ClusterIP Gateway; no EG ConfigMap patch):
    ./scripts/bootstrap-gateway.sh --skip-envoy-gateway
    ./scripts/install-production.sh --topology layered --hosts-agents ... --hosts-langfuse ...

  Shared / attach to existing Gateway:
    ./scripts/bootstrap-gateway.sh --skip-envoy-gateway --skip-ai-gateway
    ./scripts/install-quickstart.sh --topology shared --gateway-class ... --parent-ref-name ... --parent-ref-namespace ...

  Explicitly add the AI Gateway hook (mutates their EG ConfigMap):
    ./scripts/bootstrap-gateway.sh --skip-envoy-gateway --patch-extension-manager
EOF
    exit 1
  else
    echo "Envoy Gateway already ready (not Zelkor-owned); not patching envoy-gateway-config"
  fi

  if ! deployment_available envoy-gateway-system envoy-gateway; then
    wait_rollout envoy-gateway-system envoy-gateway
  fi
elif [[ "$PATCH_EXTENSION_MANAGER" -eq 1 ]]; then
  echo "WARNING: --patch-extension-manager replaces envoy-gateway-config and restarts Envoy Gateway (cluster ingress)."
  apply_extension_config
else
  echo "skip Envoy Gateway (--skip-envoy-gateway)"
fi

if [[ "$SKIP_AI_GATEWAY" -eq 0 ]]; then
  if deployment_available envoy-ai-gateway-system ai-gateway-controller; then
    echo "Envoy AI Gateway already ready; skipping Helm install"
  else
    echo "Deploying Envoy AI Gateway ${AI_GATEWAY_HELM_VERSION}..."
    helm upgrade -i aieg-crd oci://docker.io/envoyproxy/ai-gateway-crds-helm \
      "${HELM_ARGS[@]}" \
      --version "$AI_GATEWAY_HELM_VERSION" \
      --namespace envoy-ai-gateway-system \
      --create-namespace \
      --timeout "$HELM_INSTALL_TIMEOUT"

    helm upgrade -i aieg oci://docker.io/envoyproxy/ai-gateway-helm \
      "${HELM_ARGS[@]}" \
      --version "$AI_GATEWAY_HELM_VERSION" \
      --namespace envoy-ai-gateway-system \
      --create-namespace \
      --wait \
      --timeout "$HELM_INSTALL_TIMEOUT"

    zelkor_ownership_annotate_ns envoy-ai-gateway-system
    zelkor_ownership_record ai-gateway
    wait_rollout envoy-ai-gateway-system ai-gateway-controller
  fi
else
  echo "skip Envoy AI Gateway (--skip-ai-gateway)"
fi

_install_gateway_policies
_ensure_aigw_mcp_session_seed

echo "bootstrap-gateway: done"
