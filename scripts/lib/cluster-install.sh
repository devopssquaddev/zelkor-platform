# Shared helpers for existing-cluster CE installers.
# Sourced by scripts/install-quickstart.sh and scripts/install-production.sh.
# Not a customer entry point.

cluster_install_die() {
  echo "error: $*" >&2
  exit 1
}

# shellcheck source=gateway-policies.sh
source "${ZELKOR_REPO_ROOT}/scripts/lib/gateway-policies.sh"
# shellcheck source=mcp-dataplane-install.sh
source "${ZELKOR_REPO_ROOT}/scripts/lib/mcp-dataplane-install.sh"

cluster_install_need() {
  command -v "$1" >/dev/null 2>&1 || cluster_install_die "missing required command: $1"
}

cluster_install_setup_log() {
  : "${ZELKOR_REPO_ROOT:?ZELKOR_REPO_ROOT must be set before cluster_install_setup_log}"
  # shellcheck source=install-log.sh
  source "${ZELKOR_REPO_ROOT}/scripts/lib/install-log.sh"
  install_log_setup
}

cluster_install_init() {
  : "${ZELKOR_REPO_ROOT:?ZELKOR_REPO_ROOT must be set before sourcing cluster-install.sh}"
  # shellcheck source=bootstrap-ownership.sh
  source "${ZELKOR_REPO_ROOT}/scripts/lib/bootstrap-ownership.sh"
  CLUSTER_INSTALL_NAMESPACE="${CLUSTER_INSTALL_NAMESPACE:-zelkor}"
  CLUSTER_INSTALL_RELEASE="${CLUSTER_INSTALL_RELEASE:-zelkor-platform}"
  CLUSTER_INSTALL_TOPOLOGY="${CLUSTER_INSTALL_TOPOLOGY:-greenfield}"
  CLUSTER_INSTALL_DRY_RUN="${CLUSTER_INSTALL_DRY_RUN:-0}"
  CLUSTER_INSTALL_INSTALL_AI_GATEWAY="${CLUSTER_INSTALL_INSTALL_AI_GATEWAY:-0}"
  CLUSTER_INSTALL_STRICT="${CLUSTER_INSTALL_STRICT:-0}"
  CLUSTER_INSTALL_SKIP_ENVOY_GATEWAY="${CLUSTER_INSTALL_SKIP_ENVOY_GATEWAY:-0}"
  CLUSTER_INSTALL_SKIP_AI_GATEWAY="${CLUSTER_INSTALL_SKIP_AI_GATEWAY:-0}"
  CLUSTER_INSTALL_NEXTAUTH_SCHEME="${CLUSTER_INSTALL_NEXTAUTH_SCHEME:-http}"
  CLUSTER_INSTALL_PG_INSTANCES="${CLUSTER_INSTALL_PG_INSTANCES:-1}"
  CLUSTER_INSTALL_EXPECT_HA="${CLUSTER_INSTALL_EXPECT_HA:-0}"
  CLUSTER_INSTALL_ENFORCE_STORAGE="${CLUSTER_INSTALL_ENFORCE_STORAGE:-0}"
  CLUSTER_INSTALL_GVISOR_INSTALL="${CLUSTER_INSTALL_GVISOR_INSTALL:-0}"
  CLUSTER_INSTALL_GVISOR_SKIP="${CLUSTER_INSTALL_GVISOR_SKIP:-0}"
  CLUSTER_INSTALL_HELM_LAST_ERR=""
  CLUSTER_INSTALL_CLASS_NODES=""
  CLUSTER_INSTALL_RETRY_SLEEP="${CLUSTER_INSTALL_RETRY_SLEEP:-2}"
  KUBECONFIG_FILE="${KUBECONFIG_FILE:-}"
  KUBE_CONTEXT="${KUBE_CONTEXT:-}"
  HOSTS_AGENTS="${HOSTS_AGENTS:-}"
  HOSTS_LANGFUSE="${HOSTS_LANGFUSE:-}"
  PARENT_REF_NAME="${PARENT_REF_NAME:-}"
  PARENT_REF_NAMESPACE="${PARENT_REF_NAMESPACE:-}"
  GATEWAY_CLASS="${GATEWAY_CLASS:-}"
  SELECTED_OLLAMA_LOCAL_HOST="${SELECTED_OLLAMA_LOCAL_HOST:-}"
  DEFAULT_LLM_MODEL="${DEFAULT_LLM_MODEL:-}"
  LLM_PROVIDER_COUNT=0
  LLM_PROVIDER_SUMMARY=""
  KUBECTL_ARGS=()
  HELM_KUBE_ARGS=()
  CLUSTER_INSTALL_HELM_SETS=()
  CLUSTER_INSTALL_HELM_EXTRA=()
  CLUSTER_INSTALL_SHIFT=1
  JWT_ISSUER=""
  JWT_AUDIENCE=""
  JWKS_FILE=""
}

cluster_install_helm_sets_include() {
  local needle="$1"
  local sets=("${CLUSTER_INSTALL_HELM_SETS[@]+"${CLUSTER_INSTALL_HELM_SETS[@]}"}")
  local i=0 val=""
  while [[ $i -lt ${#sets[@]} ]]; do
    case "${sets[$i]}" in
      --set)
        i=$((i + 1))
        [[ $i -lt ${#sets[@]} ]] || break
        val="${sets[$i]}"
        case "$val" in
          "${needle}"*) return 0 ;;
        esac
        ;;
      --set-file|--set-string)
        i=$((i + 1))
        [[ $i -lt ${#sets[@]} ]] || break
        val="${sets[$i]}"
        case "$val" in
          "${needle}"*) return 0 ;;
        esac
        ;;
      --set-string=*)
        val="${sets[$i]#--set-string=}"
        case "$val" in
          "${needle}"*) return 0 ;;
        esac
        ;;
      --set=*)
        val="${sets[$i]#--set=}"
        case "$val" in
          "${needle}"*) return 0 ;;
        esac
        ;;
    esac
    i=$((i + 1))
  done
  return 1
}

cluster_install_jwt_source_configured() {
  cluster_install_helm_sets_include "platform.tenants.jwt.jwks=" && return 0
  cluster_install_helm_sets_include "platform.tenants.jwt.jwksConfigMap=" && return 0
  cluster_install_helm_sets_include "platform.tenants.jwt.remoteJwksUri=" && return 0
  cluster_install_helm_sets_include "platform.tenants.jwt.localSigning.enabled=" && return 0
  cluster_install_helm_sets_include "platform.tenants.jwt.localSigning.privateKey=" && return 0
  return 1
}

cluster_install_apply_jwt_cli_flags() {
  if [[ -n "$JWT_ISSUER" ]]; then
    CLUSTER_INSTALL_HELM_SETS+=(--set "platform.tenants.jwt.issuer=${JWT_ISSUER}")
  fi
  if [[ -n "$JWT_AUDIENCE" ]]; then
    CLUSTER_INSTALL_HELM_SETS+=(--set-string "platform.tenants.jwt.audiences[0]=${JWT_AUDIENCE}")
  fi
  if [[ -n "$JWKS_FILE" ]]; then
    [[ -f "$JWKS_FILE" ]] || cluster_install_die "--jwks-file not found: ${JWKS_FILE}"
    CLUSTER_INSTALL_HELM_SETS+=(--set-file "platform.tenants.jwt.jwks=${JWKS_FILE}")
  fi
}

cluster_install_require_external_jwt() {
  local values_file="$1"
  if cluster_install_profile_local_signing "$values_file"; then
    return 0
  fi
  cluster_install_helm_sets_include "platform.tenants.jwt.issuer=" || \
    cluster_install_die "production install requires --jwt-issuer or --set platform.tenants.jwt.issuer (profile has no localSigning)"
  local aud_ok=0
  if cluster_install_helm_sets_include "platform.tenants.jwt.audiences[0]="; then
    aud_ok=1
  fi
  if [[ "$aud_ok" -eq 0 ]]; then
    cluster_install_die "production install requires --jwt-audience or --set platform.tenants.jwt.audiences[0]"
  fi
  cluster_install_jwt_source_configured || \
    cluster_install_die "production install requires --jwks-file or --set platform.tenants.jwt.jwks / jwksConfigMap / remoteJwksUri"
}

cluster_install_try_common() {
  local flag="$1"
  local value="${2:-}"
  CLUSTER_INSTALL_SHIFT=1
  case "$flag" in
    --kubeconfig)
      [[ -n "$value" ]] || cluster_install_die "missing value for --kubeconfig"
      KUBECONFIG_FILE="$value"
      CLUSTER_INSTALL_SHIFT=2
      ;;
    --kube-context)
      [[ -n "$value" ]] || cluster_install_die "missing value for --kube-context"
      KUBE_CONTEXT="$value"
      CLUSTER_INSTALL_SHIFT=2
      ;;
    --namespace)
      [[ -n "$value" ]] || cluster_install_die "missing value for --namespace"
      CLUSTER_INSTALL_NAMESPACE="$value"
      CLUSTER_INSTALL_SHIFT=2
      ;;
    --release)
      [[ -n "$value" ]] || cluster_install_die "missing value for --release"
      CLUSTER_INSTALL_RELEASE="$value"
      CLUSTER_INSTALL_SHIFT=2
      ;;
    --topology)
      [[ -n "$value" ]] || cluster_install_die "missing value for --topology"
      CLUSTER_INSTALL_TOPOLOGY="$value"
      CLUSTER_INSTALL_SHIFT=2
      ;;
    --hosts-agents)
      [[ -n "$value" ]] || cluster_install_die "missing value for --hosts-agents"
      HOSTS_AGENTS="$value"
      CLUSTER_INSTALL_SHIFT=2
      ;;
    --hosts-langfuse)
      [[ -n "$value" ]] || cluster_install_die "missing value for --hosts-langfuse"
      HOSTS_LANGFUSE="$value"
      CLUSTER_INSTALL_SHIFT=2
      ;;
    --parent-ref-name)
      [[ -n "$value" ]] || cluster_install_die "missing value for --parent-ref-name"
      PARENT_REF_NAME="$value"
      CLUSTER_INSTALL_SHIFT=2
      ;;
    --parent-ref-namespace)
      [[ -n "$value" ]] || cluster_install_die "missing value for --parent-ref-namespace"
      PARENT_REF_NAMESPACE="$value"
      CLUSTER_INSTALL_SHIFT=2
      ;;
    --gateway-class)
      [[ -n "$value" ]] || cluster_install_die "missing value for --gateway-class"
      GATEWAY_CLASS="$value"
      CLUSTER_INSTALL_SHIFT=2
      ;;
    --install-ai-gateway)
      CLUSTER_INSTALL_INSTALL_AI_GATEWAY=1
      ;;
    --strict)
      CLUSTER_INSTALL_STRICT=1
      ;;
    --image-pull-secret)
      [[ -n "$value" ]] || cluster_install_die "missing value for --image-pull-secret"
      CLUSTER_INSTALL_HELM_SETS+=(--set "global.imagePullSecrets[0].name=${value}")
      CLUSTER_INSTALL_SHIFT=2
      ;;
    --dry-run)
      CLUSTER_INSTALL_DRY_RUN=1
      ;;
    --set)
      [[ -n "$value" ]] || cluster_install_die "missing value for --set"
      CLUSTER_INSTALL_HELM_SETS+=(--set "$value")
      CLUSTER_INSTALL_SHIFT=2
      ;;
    *)
      return 1
      ;;
  esac
  return 0
}

cluster_install_apply_kube_flags() {
  KUBECTL_ARGS=()
  HELM_KUBE_ARGS=()
  if [[ -n "$KUBECONFIG_FILE" ]]; then
    KUBECTL_ARGS+=(--kubeconfig "$KUBECONFIG_FILE")
    HELM_KUBE_ARGS+=(--kubeconfig "$KUBECONFIG_FILE")
  fi
  if [[ -n "$KUBE_CONTEXT" ]]; then
    KUBECTL_ARGS+=(--context "$KUBE_CONTEXT")
    HELM_KUBE_ARGS+=(--kube-context "$KUBE_CONTEXT")
  fi
}

cluster_install_validate_topology() {
  case "$CLUSTER_INSTALL_TOPOLOGY" in
    greenfield|layered|shared) ;;
    *) cluster_install_die "unknown --topology ${CLUSTER_INSTALL_TOPOLOGY} (greenfield|layered|shared)" ;;
  esac
}

cluster_install_require_shared_refs() {
  [[ "$CLUSTER_INSTALL_TOPOLOGY" == "shared" ]] || return 0
  [[ -n "$PARENT_REF_NAME" ]] || cluster_install_die "shared topology requires --parent-ref-name"
  [[ -n "$PARENT_REF_NAMESPACE" ]] || cluster_install_die "shared topology requires --parent-ref-namespace"
  [[ -n "$GATEWAY_CLASS" ]] || cluster_install_die "shared topology requires --gateway-class"
}

cluster_install_gateway_overlay() {
  case "$CLUSTER_INSTALL_TOPOLOGY" in
    greenfield) echo "${ZELKOR_REPO_ROOT}/profiles/values-gateway-greenfield.yaml" ;;
    layered) echo "${ZELKOR_REPO_ROOT}/profiles/values-gateway-layered.yaml" ;;
    shared) echo "${ZELKOR_REPO_ROOT}/profiles/values-gateway-shared.yaml" ;;
  esac
}

cluster_install_deployment_available() {
  local ns="$1"
  local name="$2"
  local available
  available=$(kubectl "${KUBECTL_ARGS[@]}" get deployment "$name" -n "$ns" \
    -o jsonpath='{.status.conditions[?(@.type=="Available")].status}' 2>/dev/null || true)
  [[ "$available" == "True" ]]
}

cluster_install_eg_owned() {
  zelkor_ownership_owns envoy-gateway || zelkor_ownership_ns_owned envoy-gateway-system
}

cluster_install_adapt_layered_bootstrap() {
  [[ "$CLUSTER_INSTALL_TOPOLOGY" == "layered" ]] || return 0
  [[ "$CLUSTER_INSTALL_DRY_RUN" -eq 1 ]] && return 0
  if cluster_install_deployment_available envoy-gateway-system envoy-gateway; then
    if ! cluster_install_eg_owned; then
      CLUSTER_INSTALL_SKIP_ENVOY_GATEWAY=1
      echo "install: layered + existing Envoy Gateway (not Zelkor-owned); skip EG install/patch"
    fi
  fi
  if cluster_install_deployment_available envoy-ai-gateway-system ai-gateway-controller; then
    CLUSTER_INSTALL_SKIP_AI_GATEWAY=1
    echo "install: Envoy AI Gateway already Available; skip AI Gateway Helm"
  fi
}

cluster_install_bootstrap_gateway_args() {
  local args=()
  if [[ -n "$KUBECONFIG_FILE" ]]; then
    args+=(--kubeconfig "$KUBECONFIG_FILE")
  fi
  if [[ -n "$KUBE_CONTEXT" ]]; then
    args+=(--kube-context "$KUBE_CONTEXT")
  fi
  if [[ "$CLUSTER_INSTALL_TOPOLOGY" == "shared" ]]; then
    args+=(--skip-envoy-gateway)
    if [[ "$CLUSTER_INSTALL_INSTALL_AI_GATEWAY" -eq 1 ]]; then
      args+=(--patch-extension-manager)
    else
      args+=(--skip-ai-gateway)
    fi
  elif [[ "$CLUSTER_INSTALL_TOPOLOGY" == "layered" ]]; then
    if [[ "$CLUSTER_INSTALL_SKIP_ENVOY_GATEWAY" -eq 1 ]]; then
      args+=(--skip-envoy-gateway)
    fi
    if [[ "$CLUSTER_INSTALL_SKIP_AI_GATEWAY" -eq 1 ]]; then
      args+=(--skip-ai-gateway)
    elif [[ "$CLUSTER_INSTALL_INSTALL_AI_GATEWAY" -eq 1 ]]; then
      args+=(--patch-extension-manager)
    fi
  fi
  if [[ ${#args[@]} -gt 0 ]]; then
    printf '%s\n' "${args[@]}"
  fi
}

cluster_install_register_llm() {
  local name="$1"
  LLM_PROVIDER_COUNT=$((LLM_PROVIDER_COUNT + 1))
  if [[ -n "$LLM_PROVIDER_SUMMARY" ]]; then
    LLM_PROVIDER_SUMMARY+=", "
  fi
  LLM_PROVIDER_SUMMARY+="$name"
}

cluster_install_resolve_llm() {
  LLM_PROVIDER_COUNT=0
  LLM_PROVIDER_SUMMARY=""
  SELECTED_OLLAMA_LOCAL_HOST=""

  if [[ -n "${OPENAI_API_KEY:-}" ]]; then cluster_install_register_llm "OpenAI"; fi
  if [[ -n "${ANTHROPIC_API_KEY:-}" ]]; then cluster_install_register_llm "Anthropic"; fi
  if [[ -n "${GEMINI_API_KEY:-}" ]]; then cluster_install_register_llm "Gemini"; fi
  if [[ -n "${OLLAMA_API_KEY:-}" ]]; then cluster_install_register_llm "Ollama Cloud"; fi
  if [[ -n "${VLLM_BACKEND_URL:-}" ]]; then cluster_install_register_llm "vLLM"; fi
  if [[ -n "${AZURE_OPENAI_API_KEY:-}" && -n "${AZURE_OPENAI_ENDPOINT:-}" ]]; then cluster_install_register_llm "Azure OpenAI"; fi
  if [[ -n "${AWS_ACCESS_KEY_ID:-}" && -n "${AWS_SECRET_ACCESS_KEY:-}" ]]; then cluster_install_register_llm "AWS Bedrock"; fi
  if [[ -n "${VERTEX_PROJECT:-}" && -n "${VERTEX_REGION:-}" ]]; then cluster_install_register_llm "Vertex AI"; fi
  if [[ -n "${COHERE_API_KEY:-}" ]]; then cluster_install_register_llm "Cohere"; fi

  if [[ -n "${OLLAMA_LOCAL_HOST:-}" ]]; then
    SELECTED_OLLAMA_LOCAL_HOST="$OLLAMA_LOCAL_HOST"
    cluster_install_register_llm "Ollama Local"
  elif [[ -n "${OLLAMA_HOST:-}" && "${OLLAMA_HOST}" != "https://ollama.com" ]]; then
    SELECTED_OLLAMA_LOCAL_HOST="$OLLAMA_HOST"
    cluster_install_register_llm "Ollama Local"
  fi

  if [[ "$LLM_PROVIDER_COUNT" -eq 0 ]]; then
    cat >&2 <<'EOF'
error: choose at least one LLM provider.

  OPENAI_API_KEY=sk-... ./scripts/install-quickstart.sh
  ANTHROPIC_API_KEY=... ./scripts/install-quickstart.sh
  GEMINI_API_KEY=... ./scripts/install-quickstart.sh
  OLLAMA_API_KEY=... ./scripts/install-quickstart.sh
  OLLAMA_LOCAL_HOST=http://host.docker.internal:11434 ./scripts/install-quickstart.sh
  VLLM_BACKEND_URL=http://host:8000/v1 ./scripts/install-quickstart.sh
  AZURE_OPENAI_API_KEY=... AZURE_OPENAI_ENDPOINT=https://res.openai.azure.com ./scripts/install-quickstart.sh
  AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=... ./scripts/install-quickstart.sh
  VERTEX_PROJECT=... VERTEX_REGION=us-central1 ./scripts/install-quickstart.sh
  COHERE_API_KEY=... ./scripts/install-quickstart.sh
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
    elif [[ -n "${AZURE_OPENAI_API_KEY:-}" && -n "${AZURE_OPENAI_ENDPOINT:-}" ]]; then
      DEFAULT_LLM_MODEL="azure/gpt-4o-mini"
    elif [[ -n "${AWS_ACCESS_KEY_ID:-}" && -n "${AWS_SECRET_ACCESS_KEY:-}" ]]; then
      DEFAULT_LLM_MODEL="bedrock/amazon.titan-text-lite-v1"
    elif [[ -n "${VERTEX_PROJECT:-}" && -n "${VERTEX_REGION:-}" ]]; then
      DEFAULT_LLM_MODEL="gemini-2.0-flash"
    elif [[ -n "${COHERE_API_KEY:-}" ]]; then
      DEFAULT_LLM_MODEL="cohere/command-r"
    fi
  fi
}

cluster_install_append_llm_helm_sets() {
  if [[ -n "${OPENAI_API_KEY:-}" ]]; then
    CLUSTER_INSTALL_HELM_SETS+=(--set "workspace.models.providers.openai.apiKey=${OPENAI_API_KEY}")
  fi
  if [[ -n "${ANTHROPIC_API_KEY:-}" ]]; then
    CLUSTER_INSTALL_HELM_SETS+=(--set "workspace.models.providers.anthropic.apiKey=${ANTHROPIC_API_KEY}")
  fi
  if [[ -n "${GEMINI_API_KEY:-}" ]]; then
    CLUSTER_INSTALL_HELM_SETS+=(--set "workspace.models.providers.gemini.apiKey=${GEMINI_API_KEY}")
  fi
  if [[ -n "${OLLAMA_API_KEY:-}" ]]; then
    CLUSTER_INSTALL_HELM_SETS+=(--set "workspace.models.providers.ollamaCloud.apiKey=${OLLAMA_API_KEY}")
  fi
  if [[ -n "$SELECTED_OLLAMA_LOCAL_HOST" ]]; then
    CLUSTER_INSTALL_HELM_SETS+=(--set "workspace.models.providers.ollamaLocal.host=${SELECTED_OLLAMA_LOCAL_HOST}")
  fi
  if [[ -n "${VLLM_BACKEND_URL:-}" ]]; then
    CLUSTER_INSTALL_HELM_SETS+=(--set "workspace.models.providers.vllm.backendUrl=${VLLM_BACKEND_URL}")
  fi
  if [[ -n "${AZURE_OPENAI_API_KEY:-}" && -n "${AZURE_OPENAI_ENDPOINT:-}" ]]; then
    CLUSTER_INSTALL_HELM_SETS+=(--set "workspace.models.providers.azure.apiKey=${AZURE_OPENAI_API_KEY}")
    CLUSTER_INSTALL_HELM_SETS+=(--set "workspace.models.providers.azure.endpoint=${AZURE_OPENAI_ENDPOINT}")
  fi
  if [[ -n "${AWS_ACCESS_KEY_ID:-}" && -n "${AWS_SECRET_ACCESS_KEY:-}" ]]; then
    CLUSTER_INSTALL_HELM_SETS+=(--set "workspace.models.providers.bedrock.accessKeyId=${AWS_ACCESS_KEY_ID}")
    CLUSTER_INSTALL_HELM_SETS+=(--set "workspace.models.providers.bedrock.secretAccessKey=${AWS_SECRET_ACCESS_KEY}")
    CLUSTER_INSTALL_HELM_SETS+=(--set "workspace.models.providers.bedrock.region=${AWS_REGION:-us-east-1}")
  fi
  if [[ -n "${VERTEX_PROJECT:-}" && -n "${VERTEX_REGION:-}" ]]; then
    CLUSTER_INSTALL_HELM_SETS+=(--set "workspace.models.providers.vertex.project=${VERTEX_PROJECT}")
    CLUSTER_INSTALL_HELM_SETS+=(--set "workspace.models.providers.vertex.region=${VERTEX_REGION}")
    if [[ -n "${VERTEX_CREDENTIALS_JSON:-}" ]]; then
      CLUSTER_INSTALL_HELM_SETS+=(--set-string "workspace.models.providers.vertex.credentialsJson=${VERTEX_CREDENTIALS_JSON}")
    fi
    if [[ "${VERTEX_ANTHROPIC:-}" == "true" ]]; then
      CLUSTER_INSTALL_HELM_SETS+=(--set "workspace.models.providers.vertex.anthropic=true")
    fi
  fi
  if [[ -n "${COHERE_API_KEY:-}" ]]; then
    CLUSTER_INSTALL_HELM_SETS+=(--set "workspace.models.providers.cohere.apiKey=${COHERE_API_KEY}")
  fi
  if [[ -n "${DEFAULT_LLM_MODEL:-}" ]]; then
    CLUSTER_INSTALL_HELM_SETS+=(--set "workspace.models.defaultModel=${DEFAULT_LLM_MODEL}")
    CLUSTER_INSTALL_HELM_SETS+=(--set "workspace.policies.nemo.model=${DEFAULT_LLM_MODEL}")
    CLUSTER_INSTALL_HELM_SETS+=(--set-string "platform.telemetry.langfuse.surfaces.llmConnection.models[0]=${DEFAULT_LLM_MODEL}")
  fi
}

cluster_install_rand_b64() {
  openssl rand -base64 32 | tr -d '\n'
}

# Hex bytes (URL-safe). Length is openssl -hex byte count (output is 2x hex chars).
cluster_install_rand_hex() {
  openssl rand -hex "${1:-24}" | tr -d '\n'
}

cluster_install_rand_hex32() {
  cluster_install_rand_hex 32
}

cluster_install_langfuse_secrets() {
  if [[ -z "${LANGFUSE_NEXTAUTH_SECRET:-}" ]]; then
    LANGFUSE_NEXTAUTH_SECRET="$(cluster_install_rand_b64)"
  fi
  if [[ -z "${LANGFUSE_SALT:-}" ]]; then
    LANGFUSE_SALT="$(cluster_install_rand_b64)"
  fi
  if [[ -z "${LANGFUSE_ENCRYPTION_KEY:-}" ]]; then
    LANGFUSE_ENCRYPTION_KEY="$(cluster_install_rand_hex32)"
  fi
  CLUSTER_INSTALL_HELM_SETS+=(
    --set "platform.telemetry.langfuse.nextauthSecret=${LANGFUSE_NEXTAUTH_SECRET}"
    --set "platform.telemetry.langfuse.salt=${LANGFUSE_SALT}"
    --set "platform.telemetry.langfuse.encryptionKey=${LANGFUSE_ENCRYPTION_KEY}"
  )
}

# Generate missing install secrets (override via env). Chart writes them to Secrets.
# Postgres/ClickHouse/SeaweedFS use hex: Langfuse embeds passwords in migration URLs
# and base64 (+ / =) breaks ClickHouse auth. WORKER_TOKEN stays base64 (bearer, not URL).
cluster_install_platform_secrets() {
  if [[ -z "${POSTGRES_PASSWORD:-}" ]]; then
    POSTGRES_PASSWORD="$(cluster_install_rand_hex 24)"
  fi
  if [[ -z "${CLICKHOUSE_PASSWORD:-}" ]]; then
    CLICKHOUSE_PASSWORD="$(cluster_install_rand_hex 24)"
  fi
  if [[ -z "${SEAWEEDFS_ACCESS_KEY:-}" ]]; then
    SEAWEEDFS_ACCESS_KEY="$(cluster_install_rand_hex 12)"
  fi
  if [[ -z "${SEAWEEDFS_SECRET_KEY:-}" ]]; then
    SEAWEEDFS_SECRET_KEY="$(cluster_install_rand_hex 24)"
  fi
  if [[ -z "${WORKER_TOKEN:-}" ]]; then
    WORKER_TOKEN="$(cluster_install_rand_b64)"
  fi
  if [[ -z "${AI_GATEWAY_CONSUMER_KEY:-}" ]]; then
    AI_GATEWAY_CONSUMER_KEY="$(cluster_install_rand_b64)"
  fi
  if [[ -z "${VALKEY_PASSWORD:-}" ]]; then
    VALKEY_PASSWORD="$(cluster_install_rand_hex 24)"
  fi
  CLUSTER_INSTALL_HELM_SETS+=(
    --set "postgresql.auth.password=${POSTGRES_PASSWORD}"
    --set "clickhouse.auth.password=${CLICKHOUSE_PASSWORD}"
    --set "valkey.auth.password=${VALKEY_PASSWORD}"
    --set "seaweedfs.auth.accessKey=${SEAWEEDFS_ACCESS_KEY}"
    --set "seaweedfs.auth.secretKey=${SEAWEEDFS_SECRET_KEY}"
    --set "workspace.tools.sandboxMCP.workerToken=${WORKER_TOKEN}"
    --set "workspace.models.consumerKey=${AI_GATEWAY_CONSUMER_KEY}"
  )
}

# In-cluster object MCP is opt-in (OBJECT_MCP_ENABLED=true). Chart default stays off.
cluster_install_object_mcp() {
  local flag="${OBJECT_MCP_ENABLED:-}"
  if [[ "$flag" != "true" && "$flag" != "1" ]]; then
    return 0
  fi
  if [[ -z "${OBJECT_S3_ACCESS_KEY:-}" ]]; then
    OBJECT_S3_ACCESS_KEY="$(cluster_install_rand_hex 12)"
  fi
  if [[ -z "${OBJECT_S3_SECRET_KEY:-}" ]]; then
    OBJECT_S3_SECRET_KEY="$(cluster_install_rand_hex 24)"
  fi
  local bucket="${OBJECT_S3_BUCKET:-zelkor-objects}"
  local rel="$CLUSTER_INSTALL_RELEASE"
  local chart="zelkor-platform"
  local fullname="$rel"
  if [[ "$rel" != *"$chart"* ]]; then
    fullname="${rel}-${chart}"
  fi
  CLUSTER_INSTALL_HELM_SETS+=(
    --set "workspace.tools.objectMCP.enabled=true"
    --set "workspace.tools.objectMCP.s3.endpoint=http://${fullname}-seaweedfs:8333"
    --set "workspace.tools.objectMCP.s3.bucket=${bucket}"
    --set "workspace.tools.objectMCP.s3.region=auto"
    --set "workspace.tools.objectMCP.s3.forcePathStyle=true"
    --set "workspace.tools.objectMCP.s3.auth.accessKey=${OBJECT_S3_ACCESS_KEY}"
    --set "workspace.tools.objectMCP.s3.auth.secretKey=${OBJECT_S3_SECRET_KEY}"
    --set "seaweedfs.objectIdentity.accessKey=${OBJECT_S3_ACCESS_KEY}"
    --set "seaweedfs.objectIdentity.secretKey=${OBJECT_S3_SECRET_KEY}"
  )
}

cluster_install_print_secret_howto() {
  local ns="$CLUSTER_INSTALL_NAMESPACE"
  local rel="$CLUSTER_INSTALL_RELEASE"
  echo
  echo "Install secrets are in cluster Secrets (override with env before install):"
  echo "  POSTGRES_PASSWORD / CLICKHOUSE_PASSWORD / VALKEY_PASSWORD / SEAWEEDFS_* / OBJECT_S3_* / WORKER_TOKEN / AI_GATEWAY_CONSUMER_KEY"
  echo "  LANGFUSE_NEXTAUTH_SECRET / LANGFUSE_SALT / LANGFUSE_ENCRYPTION_KEY"
  echo "  Langfuse project keys (when platform.telemetry.langfuse.init.enabled): ${rel}-langfuse-init / ${rel}-langfuse-otel"
  echo "  kubectl ${KUBECTL_ARGS[*]:-} -n ${ns} get secret ${rel}-postgresql -o jsonpath='{.data.password}' | base64 -d; echo"
  echo "  kubectl ${KUBECTL_ARGS[*]:-} -n ${ns} get secret ${rel}-clickhouse -o jsonpath='{.data.password}' | base64 -d; echo"
  echo "  kubectl ${KUBECTL_ARGS[*]:-} -n ${ns} get secret ${rel}-seaweedfs -o jsonpath='{.data.access-key}' | base64 -d; echo"
  echo "  kubectl ${KUBECTL_ARGS[*]:-} -n ${ns} get secret ${rel}-sandbox-worker -o jsonpath='{.data.token}' | base64 -d; echo"
  echo "  kubectl ${KUBECTL_ARGS[*]:-} -n ${ns} get secret ${rel}-langfuse-otel -o jsonpath='{.data.LANGFUSE_PUBLIC_KEY}' | base64 -d; echo"
  echo "  kubectl ${KUBECTL_ARGS[*]:-} -n ${ns} get secret ${rel}-langfuse-otel -o jsonpath='{.data.LANGFUSE_SECRET_KEY}' | base64 -d; echo"
}

cluster_install_append_host_helm_sets() {
  [[ -n "$HOSTS_AGENTS" ]] || cluster_install_die "gateway.hosts.agents is required"
  [[ -n "$HOSTS_LANGFUSE" ]] || cluster_install_die "gateway.hosts.langfuse is required"
  CLUSTER_INSTALL_HELM_SETS+=(
    --set "gateway.hosts.agents=${HOSTS_AGENTS}"
    --set "gateway.hosts.langfuse=${HOSTS_LANGFUSE}"
    --set "platform.telemetry.langfuse.nextauthUrl=${CLUSTER_INSTALL_NEXTAUTH_SCHEME}://${HOSTS_LANGFUSE}"
  )
  if [[ "$CLUSTER_INSTALL_TOPOLOGY" == "shared" ]]; then
    CLUSTER_INSTALL_HELM_SETS+=(
      --set "gateway.gatewayClassName=${GATEWAY_CLASS}"
      --set "gateway.parentRef.name=${PARENT_REF_NAME}"
      --set "gateway.parentRef.namespace=${PARENT_REF_NAMESPACE}"
    )
  fi
}

cluster_install_helm_cmd() {
  local values_file="$1"
  local overlay
  overlay="$(cluster_install_gateway_overlay)"
  local cmd=(
    helm upgrade --install "$CLUSTER_INSTALL_RELEASE"
    "${ZELKOR_REPO_ROOT}/charts/zelkor-platform"
    --namespace "$CLUSTER_INSTALL_NAMESPACE"
    --create-namespace
    -f "$values_file"
    -f "$overlay"
  )
  if [[ ${#HELM_KUBE_ARGS[@]} -gt 0 ]]; then
    cmd+=("${HELM_KUBE_ARGS[@]}")
  fi
  if [[ ${#CLUSTER_INSTALL_HELM_SETS[@]} -gt 0 ]]; then
    cmd+=("${CLUSTER_INSTALL_HELM_SETS[@]}")
  fi
  if [[ -n "${HELM_EXTRA_ARGS:-}" ]]; then
    # shellcheck disable=SC2206
    local extra=(${HELM_EXTRA_ARGS})
    cmd+=("${extra[@]}")
  fi
  if [[ ${#CLUSTER_INSTALL_HELM_EXTRA[@]} -gt 0 ]]; then
    cmd+=("${CLUSTER_INSTALL_HELM_EXTRA[@]}")
  fi
  printf '%s\n' "${cmd[@]}"
}

cluster_install_print_or_run() {
  local label="$1"
  shift
  if [[ "$CLUSTER_INSTALL_DRY_RUN" -eq 1 ]]; then
    printf '%s' "$label"
    local arg
    for arg in "$@"; do
      printf ' %s' "$arg"
    done
    printf '\n'
    return 0
  fi
  "$@"
}

cluster_install_export_gateway_policies_env() {
  if [[ "$CLUSTER_INSTALL_TOPOLOGY" == "shared" ]]; then
    export ZELKOR_SKIP_GATEWAY_POLICIES=1
    return 0
  fi
  unset ZELKOR_SKIP_GATEWAY_POLICIES
  export ZELKOR_GATEWAY_POLICIES_GATEWAY_NAME="$(
    gateway_policies_gateway_name "$CLUSTER_INSTALL_RELEASE" "$PARENT_REF_NAME"
  )"
  export ZELKOR_GATEWAY_POLICIES_GATEWAY_NAMESPACE="$(
    gateway_policies_gateway_namespace "$CLUSTER_INSTALL_NAMESPACE" "$PARENT_REF_NAMESPACE"
  )"
  GATEWAY_POLICIES_HELM_SET_SCAN=()
  local sets=("${CLUSTER_INSTALL_HELM_SETS[@]+"${CLUSTER_INSTALL_HELM_SETS[@]}"}")
  local i=0
  while [[ $i -lt ${#sets[@]} ]]; do
    case "${sets[$i]}" in
      --set)
        i=$((i + 1))
        [[ $i -lt ${#sets[@]} ]] && GATEWAY_POLICIES_HELM_SET_SCAN+=("${sets[$i]}")
        ;;
      --set=*)
        GATEWAY_POLICIES_HELM_SET_SCAN+=("${sets[$i]#--set=}")
        ;;
    esac
    i=$((i + 1))
  done
  export ZELKOR_GATEWAY_POLICIES_LISTENERS_JSON="$(gateway_policies_listeners_json)"
}

cluster_install_run_bootstrap_gateway() {
  cluster_install_export_gateway_policies_env
  local args=()
  while IFS= read -r line; do
    [[ -n "$line" ]] && args+=("$line")
  done < <(cluster_install_bootstrap_gateway_args)
  if [[ ${#args[@]} -gt 0 ]]; then
    cluster_install_print_or_run BOOTSTRAP_GATEWAY \
      "${ZELKOR_REPO_ROOT}/scripts/bootstrap-gateway.sh" "${args[@]}"
  else
    cluster_install_print_or_run BOOTSTRAP_GATEWAY \
      "${ZELKOR_REPO_ROOT}/scripts/bootstrap-gateway.sh"
  fi
  cluster_install_envoy_enable_backend_preflight
}

cluster_install_helm_template_preflight() {
  local values_file="$1"
  [[ "$CLUSTER_INSTALL_TOPOLOGY" == "shared" ]] && return 0
  local chart="${ZELKOR_REPO_ROOT}/charts/zelkor-platform"
  local tpl_extra=()
  while IFS= read -r line; do
    [[ -n "$line" ]] && tpl_extra+=("$line")
  done < <(cluster_install_helm_template_extra_args "$values_file")
  local err_file
  err_file="$(mktemp)"
  if ! helm template "$CLUSTER_INSTALL_RELEASE" "$chart" \
    --namespace "$CLUSTER_INSTALL_NAMESPACE" \
    --disable-openapi-validation \
    "${tpl_extra[@]}" >"${err_file}" 2>&1; then
    cluster_install_die "helm template failed: $(tail -n 3 "${err_file}")"
  fi
  rm -f "${err_file}"
}

cluster_install_profile_local_signing() {
  local values_file="$1"
  # shellcheck source=local-signing-helm-sets.sh
  source "${ZELKOR_REPO_ROOT}/scripts/lib/local-signing-helm-sets.sh"
  HELM_RELEASE_NAME="$CLUSTER_INSTALL_RELEASE"
  local cfg
  cfg="$(_local_signing_read_config "$values_file" 2>/dev/null || true)"
  [[ -n "$cfg" ]]
}

cluster_install_envoy_enable_backend_preflight() {
  [[ "$CLUSTER_INSTALL_DRY_RUN" -eq 1 ]] && return 0
  local native_ref=""
  local arg
  for arg in "${CLUSTER_INSTALL_HELM_SETS[@]+"${CLUSTER_INSTALL_HELM_SETS[@]}"}"; do
    case "$arg" in
      mcp.mcproute.nativeRefKind=*) native_ref="${arg#mcp.mcproute.nativeRefKind=}" ;;
      gateway.mcproute.nativeRefKind=*) native_ref="${arg#gateway.mcproute.nativeRefKind=}" ;;
    esac
  done
  if [[ -z "$native_ref" ]]; then
    native_ref="Backend"
  fi
  if [[ "$native_ref" != "Backend" ]]; then
    return 0
  fi
  if ! kubectl "${KUBECTL_ARGS[@]}" get configmap envoy-gateway-config -n envoy-gateway-system >/dev/null 2>&1; then
    return 0
  fi
  local body
  body="$(kubectl "${KUBECTL_ARGS[@]}" get configmap envoy-gateway-config -n envoy-gateway-system \
    -o jsonpath='{.data.envoy-gateway\.yaml}' 2>/dev/null || true)"
  if [[ "$body" != *"enableBackend: true"* ]]; then
    cluster_install_die "Envoy Gateway extensionApis.enableBackend must be true for MCPRoute Backend refs (re-run scripts/bootstrap-gateway.sh)"
  fi
}

cluster_install_run_helm() {
  local values_file="$1"
  cluster_install_helm_template_preflight "$values_file"
  cluster_install_gateway_policies_preflight "$values_file"
  local cmd=()
  while IFS= read -r line; do
    [[ -n "$line" ]] && cmd+=("$line")
  done < <(cluster_install_helm_cmd "$values_file")
  cluster_install_apply_helm_argv "${cmd[@]}"
}

cluster_install_append_local_signing_helm_sets() {
  local values_file="$1"
  # shellcheck source=lib/local-signing-helm-sets.sh
  source "${ZELKOR_REPO_ROOT}/scripts/lib/local-signing-helm-sets.sh"
  HELM_RELEASE_NAME="$CLUSTER_INSTALL_RELEASE"
  append_local_signing_helm_sets CLUSTER_INSTALL_HELM_SETS "$values_file"
}

cluster_install_refuse_foreign_eg() {
  [[ "$CLUSTER_INSTALL_TOPOLOGY" == "greenfield" ]] || return 0
  [[ "$CLUSTER_INSTALL_DRY_RUN" -eq 1 ]] && return 0
  cluster_install_deployment_available envoy-gateway-system envoy-gateway || return 0
  if cluster_install_eg_owned; then
    return 0
  fi
  cluster_install_die "Envoy Gateway is already running and was not installed by Zelkor. Use --topology layered (Zelkor Gateway + ClusterIP behind your ingress) or --topology shared (attach to their Gateway). Greenfield will not replace envoy-gateway-config."
}

cluster_install_warn_or_fail() {
  echo "warning: $*" >&2
  if [[ "$CLUSTER_INSTALL_STRICT" -eq 1 ]]; then
    cluster_install_die "$*"
  fi
}

cluster_install_resolved_pg_instances() {
  local arg
  local found=""
  for arg in "${CLUSTER_INSTALL_HELM_SETS[@]+"${CLUSTER_INSTALL_HELM_SETS[@]}"}"; do
    case "$arg" in
      databases.postgresql.instances=*)
        found="${arg#databases.postgresql.instances=}"
        ;;
    esac
  done
  if [[ -n "$found" ]]; then
    echo "$found"
  else
    echo "$CLUSTER_INSTALL_PG_INSTANCES"
  fi
}

cluster_install_helm_template_extra_args() {
  local values_file="$1"
  local overlay
  overlay="$(cluster_install_gateway_overlay)"
  local args=(
    -f "$values_file"
    -f "$overlay"
  )
  if [[ ${#CLUSTER_INSTALL_HELM_SETS[@]} -gt 0 ]]; then
    args+=("${CLUSTER_INSTALL_HELM_SETS[@]}")
  fi
  printf '%s\n' "${args[@]}"
}

cluster_install_gateway_policies_preflight() {
  local values_file="$1"
  [[ "$CLUSTER_INSTALL_DRY_RUN" -eq 1 ]] && return 0
  [[ "$CLUSTER_INSTALL_TOPOLOGY" == "shared" ]] && return 0
  if ! helm "${HELM_KUBE_ARGS[@]}" status zelkor-gateway-policies -n envoy-gateway-system >/dev/null 2>&1; then
    return 0
  fi
  local chart="${ZELKOR_REPO_ROOT}/charts/zelkor-platform"
  local tpl_extra=()
  while IFS= read -r line; do
    [[ -n "$line" ]] && tpl_extra+=("$line")
  done < <(cluster_install_helm_template_extra_args "$values_file")
  local expected actual
  expected="$(gateway_policies_platform_listener_ports \
    "$chart" "$CLUSTER_INSTALL_NAMESPACE" "$CLUSTER_INSTALL_RELEASE" "${tpl_extra[@]}")" || return 0
  actual="$(gateway_policies_release_listener_ports "${HELM_KUBE_ARGS[@]}")" || return 0
  if ! gateway_policies_preflight_match "$expected" "$actual"; then
    cluster_install_die "gateway listener ports (${expected}) not covered by zelkor-gateway-policies listeners (${actual})"
  fi
}

cluster_install_trim() {
  local s="$1"
  s="${s#"${s%%[![:space:]]*}"}"
  s="${s%"${s##*[![:space:]]}"}"
  printf '%s' "$s"
}

cluster_install_kubectl() {
  if [[ ${#KUBECTL_ARGS[@]} -gt 0 ]]; then
    kubectl "${KUBECTL_ARGS[@]}" "$@"
  else
    kubectl "$@"
  fi
}

cluster_install_helm_bin() {
  local cmd=(helm)
  if [[ ${#HELM_KUBE_ARGS[@]} -gt 0 ]]; then
    cmd+=("${HELM_KUBE_ARGS[@]}")
  fi
  printf '%s\n' "${cmd[@]}"
}

cluster_install_helm_set_value() {
  local key="$1"
  local i=0 val="" result="" found=1 n=0
  n=${#CLUSTER_INSTALL_HELM_SETS[@]}
  while [[ $i -lt $n ]]; do
    case "${CLUSTER_INSTALL_HELM_SETS[$i]}" in
      --set|--set-string)
        i=$((i + 1))
        if [[ $i -ge $n ]]; then
          break
        fi
        val="${CLUSTER_INSTALL_HELM_SETS[$i]}"
        case "$val" in
          "$key"=*)
            result="${val#"$key"=}"
            found=0
            ;;
        esac
        ;;
      --set=*)
        val="${CLUSTER_INSTALL_HELM_SETS[$i]#--set=}"
        case "$val" in
          "$key"=*)
            result="${val#"$key"=}"
            found=0
            ;;
        esac
        ;;
      --set-string=*)
        val="${CLUSTER_INSTALL_HELM_SETS[$i]#--set-string=}"
        case "$val" in
          "$key"=*)
            result="${val#"$key"=}"
            found=0
            ;;
        esac
        ;;
    esac
    i=$((i + 1))
  done
  if [[ $found -eq 0 ]]; then
    printf '%s' "$result"
    return 0
  fi
  return 1
}

cluster_install_count_lines() {
  local data="$1"
  if [[ -z "$data" ]]; then
    printf '0'
    return 0
  fi
  printf '%s\n' "$data" | sed '/^$/d' | wc -l | tr -d '[:space:]'
}

cluster_install_ready_node_names() {
  cluster_install_kubectl get nodes --field-selector=spec.unschedulable!=true \
    -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.status.conditions[?(@.type=="Ready")].status}{"\n"}{end}' \
    2>/dev/null | awk '$2 == "True" { print $1 }' || true
  return 0
}

cluster_install_csi_ready_node_names() {
  local driver="$1"
  local ready csi node drivers word hit
  ready="$(cluster_install_ready_node_names)"
  csi="$(cluster_install_kubectl get csinode \
    -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{range .spec.drivers[*]}{.name}{" "}{end}{"\n"}{end}' \
    2>/dev/null || true)"
  while IFS=$'\t' read -r node drivers; do
    [[ -n "$node" ]] || continue
    hit=1
    for word in $drivers; do
      if [[ "$word" == "$driver" ]]; then
        hit=0
        break
      fi
    done
    [[ "$hit" -eq 0 ]] || continue
    if printf '%s\n' "$ready" | grep -qx -- "$node"; then
      printf '%s\n' "$node"
    fi
  done <<< "$csi"
  return 0
}

cluster_install_provisioner_pods_ok() {
  local prov="$1"
  local lines name ready rest any=0 ok=0
  lines="$(cluster_install_kubectl get pods -A \
    -o jsonpath='{range .items[*]}{.metadata.name}{"|"}{.status.conditions[?(@.type=="Ready")].status}{"|"}{range .spec.containers[*]}{.name}{" "}{range .args[*]}{.}{" "}{end}{end}{"\n"}{end}' \
    2>/dev/null || true)"
  while IFS='|' read -r name ready rest; do
    [[ -n "$name" ]] || continue
    case "${name} ${rest}" in
      *"$prov"*) ;;
      *) continue ;;
    esac
    any=1
    if [[ "$ready" == "True" ]]; then
      ok=1
    fi
  done <<< "$lines"
  if [[ "$any" -eq 1 && "$ok" -eq 0 ]]; then
    return 1
  fi
  return 0
}

cluster_install_storage_set_hint() {
  printf '%s' "--set databases.postgresql.storage.storageClass --set databases.clickhouse.storage.storageClass --set seaweedfs.persistence.storageClass"
}

# topologyKeys on the CSINode plus the same labels on a Ready node that does
# not list the driver lets the scheduler place a volume where it cannot attach.
cluster_install_select_csi_nodes() {
  local sc="$1"
  local driver="$2"
  local dump node name keys topo_keys="" driver_nodes="" ready eligible=""
  local label_dump labels n key missing unsafe="" filtered=""
  dump="$(cluster_install_kubectl get csinode -o go-template='{{range .items}}{{$n := .metadata.name}}{{range .spec.drivers}}{{$n}}{{"\t"}}{{.name}}{{"\t"}}{{range .topologyKeys}}{{.}} {{end}}{{"\n"}}{{end}}{{end}}' 2>/dev/null || true)"
  if [[ -z "$dump" ]]; then
    CLUSTER_INSTALL_CLASS_NODES="$(cluster_install_csi_ready_node_names "$driver")"
    return 0
  fi
  while IFS=$'\t' read -r node name keys; do
    [[ "$name" == "$driver" ]] || continue
    driver_nodes+="${node}"$'\n'
    if [[ -z "${topo_keys// /}" && -n "${keys// /}" ]]; then
      topo_keys="$keys"
    fi
  done <<< "$dump"
  ready="$(cluster_install_ready_node_names)"
  while IFS= read -r n; do
    [[ -n "$n" ]] || continue
    if printf '%s\n' "$ready" | grep -qx -- "$n"; then
      eligible+="${n}"$'\n'
    fi
  done <<< "$driver_nodes"
  if [[ -z "${topo_keys// /}" ]]; then
    CLUSTER_INSTALL_CLASS_NODES="$eligible"
    return 0
  fi
  label_dump="$(cluster_install_kubectl get nodes -o go-template='{{range .items}}{{.metadata.name}}{{"\t"}}{{range $k, $v := .metadata.labels}}{{$k}} {{end}}{{"\n"}}{{end}}' 2>/dev/null || true)"
  while IFS=$'\t' read -r node labels; do
    [[ -n "$node" ]] || continue
    printf '%s\n' "$ready" | grep -qx -- "$node" || continue
    missing=0
    for key in $topo_keys; do
      case " ${labels} " in
        *" ${key} "*) ;;
        *) missing=1 ;;
      esac
    done
    [[ "$missing" -eq 0 ]] || continue
    if ! printf '%s\n' "$eligible" | grep -qx -- "$node"; then
      unsafe+="${node} "
    else
      filtered+="${node}"$'\n'
    fi
  done <<< "$label_dump"
  if [[ -n "${unsafe// /}" ]]; then
    cluster_install_die "StorageClass ${sc} (provisioner ${driver}) has topology keys (${topo_keys}) on Ready nodes that do not list the CSIDriver (${unsafe}). A volume can be scheduled where it cannot provision. Pass $(cluster_install_storage_set_hint)"
  fi
  CLUSTER_INSTALL_CLASS_NODES="$filtered"
}

cluster_install_require_provisionable() {
  local sc="$1"
  local prov nodes
  prov="$(cluster_install_kubectl get storageclass "$sc" -o jsonpath='{.provisioner}' 2>/dev/null || true)"
  prov="$(cluster_install_trim "$prov")"
  [[ -n "$prov" ]] || cluster_install_die "StorageClass ${sc} has no provisioner. Pass $(cluster_install_storage_set_hint)"
  if [[ "$prov" == "kubernetes.io/no-provisioner" ]]; then
    cluster_install_die "StorageClass ${sc} uses kubernetes.io/no-provisioner and cannot provision a volume. Pass $(cluster_install_storage_set_hint)"
  fi
  if ! cluster_install_provisioner_pods_ok "$prov"; then
    cluster_install_die "provisioner ${prov} has pods and none are Ready. Pass $(cluster_install_storage_set_hint)"
  fi
  if cluster_install_kubectl get csidriver "$prov" >/dev/null 2>&1; then
    cluster_install_select_csi_nodes "$sc" "$prov"
    nodes="$CLUSTER_INSTALL_CLASS_NODES"
    [[ -n "$nodes" ]] || cluster_install_die "StorageClass ${sc} (provisioner ${prov}) is not listed on any Ready node's CSINode. Pass $(cluster_install_storage_set_hint)"
  else
    nodes="$(cluster_install_ready_node_names)"
    [[ -n "$nodes" ]] || cluster_install_die "StorageClass ${sc} (provisioner ${prov}) has no Ready nodes. Pass $(cluster_install_storage_set_hint)"
  fi
  CLUSTER_INSTALL_CLASS_NODES="$nodes"
}

cluster_install_read_volume_class() {
  local key="$1"
  local val=""
  if val="$(cluster_install_helm_set_value "$key")"; then
    cluster_install_trim "$val"
    return 0
  fi
  printf '%s' ""
  return 0
}

cluster_install_storage_preflight() {
  local pg_class ch_class sw_class set_n=0 empty_msg=""
  local pg_count instances def
  pg_class="$(cluster_install_read_volume_class databases.postgresql.storage.storageClass)"
  ch_class="$(cluster_install_read_volume_class databases.clickhouse.storage.storageClass)"
  sw_class="$(cluster_install_read_volume_class seaweedfs.persistence.storageClass)"
  if [[ -n "$pg_class" ]]; then set_n=$((set_n + 1)); else empty_msg+=" --set databases.postgresql.storage.storageClass"; fi
  if [[ -n "$ch_class" ]]; then set_n=$((set_n + 1)); else empty_msg+=" --set databases.clickhouse.storage.storageClass"; fi
  if [[ -n "$sw_class" ]]; then set_n=$((set_n + 1)); else empty_msg+=" --set seaweedfs.persistence.storageClass"; fi
  if [[ "$set_n" -gt 0 && "$set_n" -lt 3 ]]; then
    cluster_install_die "storageClass is set for some volumes and empty for others. Pass${empty_msg}"
  fi
  if [[ "$set_n" -eq 0 ]]; then
    def="$(cluster_install_kubectl get storageclass \
      -o jsonpath='{range .items[?(@.metadata.annotations.storageclass\.kubernetes\.io/is-default-class=="true")]}{.metadata.name}{"\n"}{end}' \
      2>/dev/null | head -n 1 || true)"
    def="$(cluster_install_trim "$def")"
    if [[ -z "$def" ]]; then
      cluster_install_die "no default StorageClass. Pass $(cluster_install_storage_set_hint)"
    fi
    pg_class="$def"
    ch_class="$def"
    sw_class="$def"
  fi
  cluster_install_require_provisionable "$pg_class"
  pg_count="$(cluster_install_count_lines "$CLUSTER_INSTALL_CLASS_NODES")"
  if [[ "$ch_class" != "$pg_class" ]]; then
    cluster_install_require_provisionable "$ch_class"
  fi
  if [[ "$sw_class" != "$pg_class" && "$sw_class" != "$ch_class" ]]; then
    cluster_install_require_provisionable "$sw_class"
  fi
  instances="$(cluster_install_resolved_pg_instances)"
  instances="$(cluster_install_trim "$instances")"
  case "$instances" in
    ''|*[!0-9]*)
      cluster_install_die "databases.postgresql.instances must be a positive integer (got ${instances})"
      ;;
  esac
  if [[ "$pg_count" -lt "$instances" ]]; then
    cluster_install_die "databases.postgresql.instances (${instances}) is greater than Ready nodes that can provision StorageClass ${pg_class} (${pg_count}). Pass --set databases.postgresql.instances=${pg_count} or choose a StorageClass present on more nodes."
  fi
}

cluster_install_helm_release_status() {
  local i out status rc
  local cmd=()
  while IFS= read -r line; do
    [[ -n "$line" ]] && cmd+=("$line")
  done < <(cluster_install_helm_bin)
  cmd+=(status "$CLUSTER_INSTALL_RELEASE" --namespace "$CLUSTER_INSTALL_NAMESPACE")
  for i in 1 2 3; do
    set +e
    out="$("${cmd[@]}" 2>&1)"
    rc=$?
    set -e
    if [[ "$rc" -eq 0 ]]; then
      status="$(printf '%s\n' "$out" | awk -F': ' '/^STATUS:/{print $2; exit}')"
      status="$(cluster_install_trim "$status")"
      if [[ -n "$status" ]]; then
        printf '%s' "$status"
        return 0
      fi
    fi
    case "$out" in
      *EOF*|*"connection reset"*|*"i/o timeout"*|*"unexpected EOF"*|"") ;;
      *) break ;;
    esac
  done
  printf '%s' ""
  return 0
}

cluster_install_helm_err_is_transient() {
  local err="${1:-}"
  if [[ -z "$err" ]]; then
    return 0
  fi
  case "$err" in
    *EOF*|*"connection reset"*|*"i/o timeout"*|*"Client.Timeout"*|*"unexpected EOF"*|*"http2: client connection lost"*|*"the server was unable to return"*|*"context deadline exceeded"*)
      return 0
      ;;
  esac
  return 1
}

cluster_install_helm_cli_prefix() {
  local prefix="helm" a
  if [[ ${#HELM_KUBE_ARGS[@]} -gt 0 ]]; then
    for a in "${HELM_KUBE_ARGS[@]}"; do
      prefix+=" ${a}"
    done
  fi
  printf '%s' "$prefix"
}

cluster_install_helm_clear_pending() {
  local status="$1"
  local cmd=()
  while IFS= read -r line; do
    [[ -n "$line" ]] && cmd+=("$line")
  done < <(cluster_install_helm_bin)
  case "$status" in
    pending-upgrade|pending-rollback)
      echo "install: helm release ${status}; rolling back" >&2
      cmd+=(rollback "$CLUSTER_INSTALL_RELEASE" --namespace "$CLUSTER_INSTALL_NAMESPACE")
      ;;
    pending-install)
      echo "install: helm release pending-install; uninstalling incomplete release" >&2
      cmd+=(uninstall "$CLUSTER_INSTALL_RELEASE" --namespace "$CLUSTER_INSTALL_NAMESPACE")
      ;;
    *)
      return 0
      ;;
  esac
  set +e
  "${cmd[@]}"
  set -e
  return 0
}

cluster_install_die_if_helm_pending() {
  local status
  status="$(cluster_install_helm_release_status)"
  case "$status" in
    pending-upgrade|pending-rollback)
      cluster_install_die "helm release left ${status}. Run: $(cluster_install_helm_cli_prefix) rollback ${CLUSTER_INSTALL_RELEASE} --namespace ${CLUSTER_INSTALL_NAMESPACE}"
      ;;
    pending-install)
      cluster_install_die "helm release left pending-install. Run: $(cluster_install_helm_cli_prefix) uninstall ${CLUSTER_INSTALL_RELEASE} --namespace ${CLUSTER_INSTALL_NAMESPACE}"
      ;;
  esac
}

cluster_install_helm_capture() {
  local err_file rc
  err_file="$(mktemp)"
  set +e
  "$@" 2>&1 | tee "$err_file"
  rc=${PIPESTATUS[0]}
  CLUSTER_INSTALL_HELM_LAST_ERR="$(cat "$err_file" 2>/dev/null || true)"
  rm -f "$err_file"
  return "$rc"
}

cluster_install_helm_with_recovery() {
  local attempt=1 max=3 rc=0 status="" retry=0
  while [[ "$attempt" -le "$max" ]]; do
    set +e
    cluster_install_helm_capture "$@"
    rc=$?
    set -e
    if [[ "$rc" -eq 0 ]]; then
      return 0
    fi
    status="$(cluster_install_helm_release_status)"
    cluster_install_helm_clear_pending "$status"
    retry=0
    if cluster_install_helm_err_is_transient "${CLUSTER_INSTALL_HELM_LAST_ERR:-}"; then
      retry=1
    fi
    case "$status" in
      pending-*) retry=1 ;;
    esac
    if [[ "$retry" -eq 0 || "$attempt" -eq "$max" ]]; then
      break
    fi
    echo "install: retrying helm (${attempt}/${max})" >&2
    if [[ "${CLUSTER_INSTALL_RETRY_SLEEP:-2}" != "0" ]]; then
      sleep "$CLUSTER_INSTALL_RETRY_SLEEP"
    fi
    attempt=$((attempt + 1))
  done
  cluster_install_die_if_helm_pending
  return "$rc"
}

cluster_install_apply_helm_argv() {
  if [[ "$CLUSTER_INSTALL_DRY_RUN" -eq 1 ]]; then
    cluster_install_print_or_run HELM "$@"
    return 0
  fi
  cluster_install_helm_with_recovery "$@"
}

cluster_install_preflight() {
  [[ "$CLUSTER_INSTALL_DRY_RUN" -eq 1 ]] && return 0
  local sc_default ready_nodes instances metrics
  if [[ "${CLUSTER_INSTALL_ENFORCE_STORAGE:-0}" -eq 1 ]]; then
    cluster_install_storage_preflight
  else
    sc_default=$(kubectl "${KUBECTL_ARGS[@]}" get storageclass \
      -o jsonpath='{range .items[?(@.metadata.annotations.storageclass\.kubernetes\.io/is-default-class=="true")]}{.metadata.name}{"\n"}{end}' \
      2>/dev/null || true)
    if [[ -z "$sc_default" ]]; then
      cluster_install_warn_or_fail "no default StorageClass; set databases.postgresql.storage.storageClass and databases.clickhouse.storage.storageClass"
    fi
    ready_nodes=$(kubectl "${KUBECTL_ARGS[@]}" get nodes \
      --field-selector=spec.unschedulable!=true \
      -o jsonpath='{range .items[*]}{.status.conditions[?(@.type=="Ready")].status}{"\n"}{end}' \
      2>/dev/null | grep -c '^True$' || true)
    instances="$(cluster_install_resolved_pg_instances)"
    if [[ "$ready_nodes" -lt "$instances" ]]; then
      cluster_install_warn_or_fail "Ready nodes (${ready_nodes}) < databases.postgresql.instances (${instances}); pass --set databases.postgresql.instances=${ready_nodes} or add schedulable nodes"
    fi
  fi
  if [[ "$CLUSTER_INSTALL_EXPECT_HA" -eq 1 ]]; then
    metrics=$(kubectl "${KUBECTL_ARGS[@]}" get apiservice v1beta1.metrics.k8s.io \
      -o jsonpath='{.status.conditions[?(@.type=="Available")].status}' 2>/dev/null || true)
    if [[ "$metrics" != "True" ]]; then
      cluster_install_warn_or_fail "metrics-server API is not Available (required for highAvailability HPA)"
    fi
  fi
}

cluster_install_adopt_gatewayclass() {
  [[ "$CLUSTER_INSTALL_DRY_RUN" -eq 1 ]] && return 0
  local arg skip=0 name="${GATEWAY_CLASS:-eg}"
  for arg in "${CLUSTER_INSTALL_HELM_SETS[@]+"${CLUSTER_INSTALL_HELM_SETS[@]}"}"; do
    case "$arg" in
      gateway.createGatewayClass=*) skip=1 ;;
      gateway.gatewayClassName=*) name="${arg#gateway.gatewayClassName=}" ;;
    esac
  done
  [[ "$skip" -eq 1 ]] && return 0
  if kubectl "${KUBECTL_ARGS[@]}" get gatewayclass "$name" >/dev/null 2>&1; then
    echo "install: GatewayClass ${name} already exists; skipping chart emit (gateway.createGatewayClass=false)"
    CLUSTER_INSTALL_HELM_SETS+=(--set "gateway.createGatewayClass=false")
  fi
}

cluster_install_gvisor_preflight() {
  [[ "$CLUSTER_INSTALL_DRY_RUN" -eq 1 ]] && return 0
  export GVISOR_HELM_RELEASE="$CLUSTER_INSTALL_RELEASE"
  export GVISOR_HELM_NAMESPACE="$CLUSTER_INSTALL_NAMESPACE"
  local args=()
  local line pending="" skip_mode=0 skip_rc=0
  local arg
  for arg in "${CLUSTER_INSTALL_HELM_SETS[@]+"${CLUSTER_INSTALL_HELM_SETS[@]}"}"; do
    case "$arg" in
      security.sandbox.provisioning.mode=*) skip_mode=1 ;;
      security.sandbox.createRuntimeClass=*) skip_rc=1 ;;
    esac
  done
  if [[ -n "$KUBECONFIG_FILE" ]]; then
    args+=(--kubeconfig "$KUBECONFIG_FILE")
  fi
  if [[ -n "$KUBE_CONTEXT" ]]; then
    args+=(--kube-context "$KUBE_CONTEXT")
  fi
  while IFS= read -r line; do
    if [[ "$line" == "--set" ]]; then
      pending="--set"
      continue
    fi
    [[ "$pending" == "--set" ]] || continue
    pending=""
    if [[ "$line" == security.sandbox.provisioning.mode=* && "$skip_mode" -eq 1 ]]; then
      continue
    fi
    if [[ "$line" == security.sandbox.createRuntimeClass=* && "$skip_rc" -eq 1 ]]; then
      continue
    fi
    CLUSTER_INSTALL_HELM_SETS+=(--set "$line")
  done < <("${ZELKOR_REPO_ROOT}/scripts/gvisor-preflight.sh" "${args[@]}" --output helm)
}

# Returns 0 and sets CLUSTER_INSTALL_SHIFT when $1 is a gVisor install flag.
cluster_install_try_gvisor_flag() {
  case "$1" in
    --install-gvisor)
      CLUSTER_INSTALL_GVISOR_INSTALL=1
      CLUSTER_INSTALL_SHIFT=1
      return 0
      ;;
    --skip-gvisor)
      CLUSTER_INSTALL_GVISOR_SKIP=1
      CLUSTER_INSTALL_SHIFT=1
      return 0
      ;;
  esac
  return 1
}

cluster_install_gvisor_resolved_mode() {
  local mode="" arg pending=""
  pending=""
  for arg in "${CLUSTER_INSTALL_HELM_SETS[@]+"${CLUSTER_INSTALL_HELM_SETS[@]}"}"; do
    if [[ "$arg" == "--set" ]]; then
      pending="--set"
      continue
    fi
    if [[ "$pending" == "--set" ]]; then
      pending=""
      case "$arg" in
        security.sandbox.provisioning.mode=*)
          mode="${arg#security.sandbox.provisioning.mode=}"
          ;;
      esac
    fi
  done
  printf '%s\n' "$mode"
}

cluster_install_gvisor_has_selector() {
  local arg pending=""
  pending=""
  for arg in "${CLUSTER_INSTALL_HELM_SETS[@]+"${CLUSTER_INSTALL_HELM_SETS[@]}"}"; do
    if [[ "$arg" == "--set" ]]; then
      pending="--set"
      continue
    fi
    if [[ "$pending" == "--set" ]]; then
      pending=""
      case "$arg" in
        security.sandbox.nodes.selector.*) return 0 ;;
      esac
    fi
  done
  return 1
}

# Prints kubectl -l arguments, one token per line, for the sandbox node selector.
cluster_install_gvisor_selector_flags() {
  local arg pending="" key val
  pending=""
  for arg in "${CLUSTER_INSTALL_HELM_SETS[@]+"${CLUSTER_INSTALL_HELM_SETS[@]}"}"; do
    if [[ "$arg" == "--set" ]]; then
      pending="--set"
      continue
    fi
    if [[ "$pending" == "--set" ]]; then
      pending=""
      case "$arg" in
        security.sandbox.nodes.selector.*)
          key="${arg#security.sandbox.nodes.selector.}"
          val="${key#*=}"
          key="${key%%=*}"
          key="${key//\\/}"
          printf '%s\n' "-l" "${key}=${val}"
          ;;
      esac
    fi
  done
}

cluster_install_gvisor_node_names() {
  local -a label_args=()
  local line
  while IFS= read -r line; do
    [[ -n "$line" ]] && label_args+=("$line")
  done < <(cluster_install_gvisor_selector_flags)
  kubectl ${KUBECTL_ARGS[@]+"${KUBECTL_ARGS[@]}"} get nodes ${label_args[@]+"${label_args[@]}"} \
    -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}'
}

cluster_install_gvisor_choose() {
  if [[ "$CLUSTER_INSTALL_GVISOR_INSTALL" -eq 1 && "$CLUSTER_INSTALL_GVISOR_SKIP" -eq 1 ]]; then
    cluster_install_die "pass only one of --install-gvisor and --skip-gvisor"
  fi

  if [[ "$CLUSTER_INSTALL_GVISOR_SKIP" -eq 1 ]]; then
    CLUSTER_INSTALL_HELM_SETS+=(
      --set "security.sandbox.enabled=false"
      --set "security.sandbox.provisioning.mode=none"
    )
    echo "install: --skip-gvisor: sandbox workers run without gVisor. Generated code is not kernel-isolated."
    return 0
  fi

  local mode
  mode="$(cluster_install_gvisor_resolved_mode)"
  if [[ "$mode" == "preinstalled" ]]; then
    echo "install: gVisor runtime is already on this cluster. Nodes will not be changed."
    if [[ "$CLUSTER_INSTALL_GVISOR_INSTALL" -eq 1 ]]; then
      echo "install: --install-gvisor is not needed; leaving the existing runtime in place."
    fi
    return 0
  fi

  if [[ "$CLUSTER_INSTALL_GVISOR_INSTALL" -eq 1 || "$mode" == "daemonset" ]]; then
    cluster_install_gvisor_require_pool
    CLUSTER_INSTALL_HELM_SETS+=(--set "security.sandbox.provisioning.mode=daemonset")
    return 0
  fi

  cat <<'EOF' >&2
install: gVisor is not on this cluster. Installing it restarts the container runtime on the nodes you select.

  --install-gvisor --set security.sandbox.nodes.selector.kubernetes\.io/hostname=NODE

Or install without kernel isolation:

  --skip-gvisor
EOF
  exit 1
}

cluster_install_gvisor_require_pool() {
  local names count
  if ! cluster_install_gvisor_has_selector; then
    if [[ "$CLUSTER_INSTALL_DRY_RUN" -eq 1 ]]; then
      cluster_install_die "--install-gvisor needs security.sandbox.nodes.selector (dry-run does not count nodes)"
    fi
    names="$(cluster_install_gvisor_node_names)"
    count="$(printf '%s\n' "$names" | grep -c . || true)"
    if [[ "$count" -le 1 && -n "$names" ]]; then
      echo "install: gVisor will restart the container runtime on:"
      printf '%s\n' "$names"
      return 0
    fi
    echo "install: refusing to restart the container runtime on every node:" >&2
    printf '%s\n' "$names" >&2
    cluster_install_die "set security.sandbox.nodes.selector to a sandbox pool, or pass --skip-gvisor"
  fi
  if [[ "$CLUSTER_INSTALL_DRY_RUN" -eq 1 ]]; then
    echo "install: gVisor will restart the container runtime on nodes matching security.sandbox.nodes.selector."
    return 0
  fi
  names="$(cluster_install_gvisor_node_names)"
  if [[ -z "$names" ]]; then
    cluster_install_die "no nodes match security.sandbox.nodes.selector"
  fi
  echo "install: gVisor will install runsc and restart the container runtime on:"
  printf '%s\n' "$names"
}

cluster_install_dataplane_name() {
  echo "${CLUSTER_INSTALL_NAMESPACE}-${CLUSTER_INSTALL_RELEASE}-dataplane"
}

cluster_install_dataplane_fqdn() {
  echo "$(cluster_install_dataplane_name).envoy-gateway-system.svc.cluster.local"
}

cluster_install_print_dataplane() {
  local name fqdn scheme
  name="$(cluster_install_dataplane_name)"
  fqdn="$(cluster_install_dataplane_fqdn)"
  scheme="${CLUSTER_INSTALL_NEXTAUTH_SCHEME}"
  echo
  echo "Envoy dataplane Service (stable name): ${fqdn}:80"
  if [[ "$CLUSTER_INSTALL_TOPOLOGY" == "layered" ]]; then
    echo "Point your existing ingress at that ClusterIP Service and preserve the Host header."
    echo "Zelkor does not apply this Ingress. Apply it yourself:"
    cat <<EOF
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: ${CLUSTER_INSTALL_RELEASE}-envoy
  namespace: envoy-gateway-system
spec:
  rules:
  - host: ${HOSTS_AGENTS}
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: ${name}
            port:
              number: 80
  - host: ${HOSTS_LANGFUSE}
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: ${name}
            port:
              number: 80
EOF
    echo "Health:"
    echo "  ${scheme}://${HOSTS_AGENTS}/health"
    echo "  ${scheme}://${HOSTS_LANGFUSE}/api/public/health"
  fi
}

cluster_install_wait_langfuse() {
  [[ "$CLUSTER_INSTALL_DRY_RUN" -eq 1 ]] && return 0
  if ! kubectl "${KUBECTL_ARGS[@]}" -n "$CLUSTER_INSTALL_NAMESPACE" \
    get deploy "${CLUSTER_INSTALL_RELEASE}-langfuse" >/dev/null 2>&1; then
    return 0
  fi
  echo "install: waiting for Langfuse Deployment"
  kubectl "${KUBECTL_ARGS[@]}" -n "$CLUSTER_INSTALL_NAMESPACE" \
    rollout status "deploy/${CLUSTER_INSTALL_RELEASE}-langfuse" --timeout=10m || \
    cluster_install_warn_or_fail "Langfuse Deployment not Ready"
}

cluster_install_wait_langfuse_bootstrap() {
  [[ "$CLUSTER_INSTALL_DRY_RUN" -eq 1 ]] && return 0
  local job="${CLUSTER_INSTALL_RELEASE}-langfuse-bootstrap"
  if ! kubectl "${KUBECTL_ARGS[@]}" -n "$CLUSTER_INSTALL_NAMESPACE" \
    get job "$job" >/dev/null 2>&1; then
    return 0
  fi
  echo "install: waiting for Langfuse bootstrap Job"
  kubectl "${KUBECTL_ARGS[@]}" -n "$CLUSTER_INSTALL_NAMESPACE" \
    wait "job/${job}" --for=condition=complete --timeout=20m || \
    cluster_install_warn_or_fail "Langfuse bootstrap Job did not complete"
}

cluster_install_wait_mcp_dataplane() {
  [[ "$CLUSTER_INSTALL_DRY_RUN" -eq 1 ]] && return 0
  MCP_DP_KUBECTL_ARGS=("${KUBECTL_ARGS[@]}")
  MCP_DP_RELEASE="$CLUSTER_INSTALL_RELEASE"
  MCP_DP_NAMESPACE="$CLUSTER_INSTALL_NAMESPACE"
  MCP_DP_KUBE_CONTEXT="${KUBE_CONTEXT:-}"
  mcp_dataplane_wait_all
}

cluster_install_print_mcp_token_banner() {
  local values_file="$1"
  MCP_DP_LOCAL_SIGNING=0
  if cluster_install_profile_local_signing "$values_file"; then
    MCP_DP_LOCAL_SIGNING=1
  fi
  MCP_DP_RELEASE="$CLUSTER_INSTALL_RELEASE"
  MCP_DP_NAMESPACE="$CLUSTER_INSTALL_NAMESPACE"
  MCP_DP_KUBE_CONTEXT="${KUBE_CONTEXT:-}"
  mcp_dataplane_print_token_banner
}

cluster_install_enable_langfuse_public_route() {
  local values_file="$1"
  [[ "$CLUSTER_INSTALL_DRY_RUN" -eq 1 ]] && return 0
  if ! kubectl "${KUBECTL_ARGS[@]}" -n "$CLUSTER_INSTALL_NAMESPACE" \
    get deploy "${CLUSTER_INSTALL_RELEASE}-langfuse" >/dev/null 2>&1; then
    return 0
  fi
  echo "install: enabling Langfuse public HTTPRoute after bootstrap"
  local cmd=()
  while IFS= read -r line; do
    [[ -n "$line" ]] && cmd+=("$line")
  done < <(cluster_install_helm_cmd "$values_file")
  cmd+=(--set "platform.telemetry.langfuse.publicHttpRoute.enabled=true")
  cluster_install_apply_helm_argv "${cmd[@]}"
}

cluster_install_prepare() {
  cluster_install_need kubectl
  cluster_install_need helm
  cluster_install_need openssl
  cluster_install_apply_kube_flags
  cluster_install_validate_topology
  cluster_install_require_shared_refs
  cluster_install_refuse_foreign_eg
  cluster_install_adapt_layered_bootstrap
  cluster_install_gvisor_preflight
  cluster_install_adopt_gatewayclass
  cluster_install_preflight
  cluster_install_resolve_llm
  cluster_install_append_llm_helm_sets
  cluster_install_langfuse_secrets
  cluster_install_platform_secrets
  cluster_install_object_mcp
  cluster_install_append_host_helm_sets
}
