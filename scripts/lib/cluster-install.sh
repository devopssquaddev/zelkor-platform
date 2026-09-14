# Shared helpers for existing-cluster CE installers.
# Sourced by scripts/install-quickstart.sh and scripts/install-production.sh.
# Not a customer entry point.

cluster_install_die() {
  echo "error: $*" >&2
  exit 1
}

cluster_install_need() {
  command -v "$1" >/dev/null 2>&1 || cluster_install_die "missing required command: $1"
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

  if [[ -n "${AZURE_OPENAI_API_KEY:-}" || -n "${AZURE_OPENAI_ENDPOINT:-}" ]]; then
    cluster_install_die "Azure OpenAI env vars are not supported in the CE gateway chart yet. Use OPENAI_API_KEY, OLLAMA_API_KEY, or OLLAMA_LOCAL_HOST."
  fi
  if [[ -n "${AWS_ACCESS_KEY_ID:-}" && -n "${AWS_SECRET_ACCESS_KEY:-}" ]]; then
    cluster_install_die "AWS Bedrock env vars are not supported in the CE gateway chart yet. Use OPENAI_API_KEY, OLLAMA_API_KEY, or OLLAMA_LOCAL_HOST."
  fi

  if [[ -n "${OPENAI_API_KEY:-}" ]]; then cluster_install_register_llm "OpenAI"; fi
  if [[ -n "${ANTHROPIC_API_KEY:-}" ]]; then cluster_install_register_llm "Anthropic"; fi
  if [[ -n "${GEMINI_API_KEY:-}" ]]; then cluster_install_register_llm "Gemini"; fi
  if [[ -n "${OLLAMA_API_KEY:-}" ]]; then cluster_install_register_llm "Ollama Cloud"; fi
  if [[ -n "${VLLM_BACKEND_URL:-}" ]]; then cluster_install_register_llm "vLLM"; fi

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
}

cluster_install_append_llm_helm_sets() {
  if [[ -n "${OPENAI_API_KEY:-}" ]]; then
    CLUSTER_INSTALL_HELM_SETS+=(--set "aiGateway.providers.openai.apiKey=${OPENAI_API_KEY}")
  fi
  if [[ -n "${ANTHROPIC_API_KEY:-}" ]]; then
    CLUSTER_INSTALL_HELM_SETS+=(--set "aiGateway.providers.anthropic.apiKey=${ANTHROPIC_API_KEY}")
  fi
  if [[ -n "${GEMINI_API_KEY:-}" ]]; then
    CLUSTER_INSTALL_HELM_SETS+=(--set "aiGateway.providers.gemini.apiKey=${GEMINI_API_KEY}")
  fi
  if [[ -n "${OLLAMA_API_KEY:-}" ]]; then
    CLUSTER_INSTALL_HELM_SETS+=(--set "aiGateway.providers.ollamaCloud.apiKey=${OLLAMA_API_KEY}")
  fi
  if [[ -n "$SELECTED_OLLAMA_LOCAL_HOST" ]]; then
    CLUSTER_INSTALL_HELM_SETS+=(--set "aiGateway.providers.ollamaLocal.host=${SELECTED_OLLAMA_LOCAL_HOST}")
  fi
  if [[ -n "${VLLM_BACKEND_URL:-}" ]]; then
    CLUSTER_INSTALL_HELM_SETS+=(--set "aiGateway.providers.vllm.backendUrl=${VLLM_BACKEND_URL}")
  fi
  if [[ -n "${DEFAULT_LLM_MODEL:-}" ]]; then
    CLUSTER_INSTALL_HELM_SETS+=(--set "guardrails.nemo.model=${DEFAULT_LLM_MODEL}")
    CLUSTER_INSTALL_HELM_SETS+=(--set-string "langfuse.surfaces.llmConnection.models[0]=${DEFAULT_LLM_MODEL}")
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
    --set "langfuse.nextauthSecret=${LANGFUSE_NEXTAUTH_SECRET}"
    --set "langfuse.salt=${LANGFUSE_SALT}"
    --set "langfuse.encryptionKey=${LANGFUSE_ENCRYPTION_KEY}"
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
  CLUSTER_INSTALL_HELM_SETS+=(
    --set "postgresql.auth.password=${POSTGRES_PASSWORD}"
    --set "clickhouse.auth.password=${CLICKHOUSE_PASSWORD}"
    --set "seaweedfs.auth.accessKey=${SEAWEEDFS_ACCESS_KEY}"
    --set "seaweedfs.auth.secretKey=${SEAWEEDFS_SECRET_KEY}"
    --set "mcp.sandboxMCP.workerToken=${WORKER_TOKEN}"
  )
}

cluster_install_print_secret_howto() {
  local ns="$CLUSTER_INSTALL_NAMESPACE"
  local rel="$CLUSTER_INSTALL_RELEASE"
  echo
  echo "Install secrets are in cluster Secrets (override with env before install):"
  echo "  POSTGRES_PASSWORD / CLICKHOUSE_PASSWORD / SEAWEEDFS_* / WORKER_TOKEN"
  echo "  LANGFUSE_NEXTAUTH_SECRET / LANGFUSE_SALT / LANGFUSE_ENCRYPTION_KEY"
  echo "  kubectl ${KUBECTL_ARGS[*]:-} -n ${ns} get secret ${rel}-postgresql -o jsonpath='{.data.password}' | base64 -d; echo"
  echo "  kubectl ${KUBECTL_ARGS[*]:-} -n ${ns} get secret ${rel}-clickhouse -o jsonpath='{.data.password}' | base64 -d; echo"
  echo "  kubectl ${KUBECTL_ARGS[*]:-} -n ${ns} get secret ${rel}-seaweedfs -o jsonpath='{.data.access-key}' | base64 -d; echo"
  echo "  kubectl ${KUBECTL_ARGS[*]:-} -n ${ns} get secret ${rel}-sandbox-worker -o jsonpath='{.data.token}' | base64 -d; echo"
}

cluster_install_append_host_helm_sets() {
  [[ -n "$HOSTS_AGENTS" ]] || cluster_install_die "gateway.hosts.agents is required"
  [[ -n "$HOSTS_LANGFUSE" ]] || cluster_install_die "gateway.hosts.langfuse is required"
  CLUSTER_INSTALL_HELM_SETS+=(
    --set "gateway.hosts.agents=${HOSTS_AGENTS}"
    --set "gateway.hosts.langfuse=${HOSTS_LANGFUSE}"
    --set "langfuse.nextauthUrl=${CLUSTER_INSTALL_NEXTAUTH_SCHEME}://${HOSTS_LANGFUSE}"
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

cluster_install_run_bootstrap_gateway() {
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
}

cluster_install_run_helm() {
  local values_file="$1"
  local cmd=()
  while IFS= read -r line; do
    [[ -n "$line" ]] && cmd+=("$line")
  done < <(cluster_install_helm_cmd "$values_file")
  cluster_install_print_or_run HELM "${cmd[@]}"
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

cluster_install_preflight() {
  [[ "$CLUSTER_INSTALL_DRY_RUN" -eq 1 ]] && return 0
  local sc_default ready_nodes instances metrics
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

cluster_install_dataplane_name() {
  echo "${CLUSTER_INSTALL_NAMESPACE}-${CLUSTER_INSTALL_RELEASE}-dataplane"
}

cluster_install_dataplane_fqdn() {
  echo "$(cluster_install_dataplane_name).envoy-gateway-system.svc.cluster.local"
}

cluster_install_print_dataplane() {
  local fqdn
  fqdn="$(cluster_install_dataplane_fqdn)"
  echo
  echo "Envoy dataplane Service (stable name): ${fqdn}:80"
  if [[ "$CLUSTER_INSTALL_TOPOLOGY" == "layered" ]]; then
    echo "Point your existing ingress at that ClusterIP Service and preserve the Host header."
    echo "Zelkor does not create Ingress objects."
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
  cluster_install_append_host_helm_sets
}
