#!/usr/bin/env bash
# Zelkor install engine — cluster bootstrap logic (kind, Helm, rollouts).
# Called by ./install.sh. For plain logs: INSTALL_UX=plain or run this script directly.
#
# Prerequisites: docker, kind, helm, kubectl

set -euo pipefail

ZELKOR_REPO_ROOT="${ZELKOR_REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$ZELKOR_REPO_ROOT"

START_TIME="${START_TIME:-$(date +%s)}"
INSTALL_START_TIME=$START_TIME
DOWNLOAD_DURATION=0

_ux_hook() {
  [[ "${INSTALL_UX_RICH:-}" == "true" ]] || return 0
  local fn="ux_${1}"
  shift
  declare -f "$fn" >/dev/null 2>&1 && "$fn" "$@"
}

CLUSTER_NAME="${CLUSTER_NAME:-zelkor}"
CHART_PATH="${CHART_PATH:-charts/zelkor-platform}"
INSTALL_PROFILE="${INSTALL_PROFILE:-fast}"
# Empty = kind CLI default node image (latest for the installed kind). Override with KIND_NODE_IMAGE=kindest/node:<tag>.
KIND_NODE_IMAGE="${KIND_NODE_IMAGE:-}"
FINSERVE_CHART_PATH="${FINSERVE_CHART_PATH:-examples/finserve/chart}"
FINSERVE_VALUES_FILE="${FINSERVE_VALUES_FILE:-${FINSERVE_CHART_PATH}/values-local.yaml}"
FINSERVE_PLATFORM_OVERLAY="${FINSERVE_PLATFORM_OVERLAY:-${FINSERVE_CHART_PATH}/values-platform-overlay.yaml}"
BUILD_IMAGES="${BUILD_IMAGES:-false}"
KIND_LOAD_IMAGES="${KIND_LOAD_IMAGES:-false}"
PREFETCH_IMAGES="${PREFETCH_IMAGES:-true}"
PREFETCH_KIND_LOAD="${PREFETCH_KIND_LOAD:-false}"
LOCAL_REGISTRY="${LOCAL_REGISTRY:-true}"
LOCAL_REGISTRY_DOCKER_NAME="${LOCAL_REGISTRY_DOCKER_NAME:-zelkor-registry-docker}"
LOCAL_REGISTRY_GHCR_NAME="${LOCAL_REGISTRY_GHCR_NAME:-zelkor-registry-ghcr}"
LOCAL_REGISTRY_DOCKER_PORT="${LOCAL_REGISTRY_DOCKER_PORT:-5000}"
LOCAL_REGISTRY_GHCR_PORT="${LOCAL_REGISTRY_GHCR_PORT:-5001}"
LOCAL_REGISTRY_BIND="${LOCAL_REGISTRY_BIND:-127.0.0.1}"
INSTALL_TIMINGS_FILE="${INSTALL_TIMINGS_FILE:-/tmp/zelkor-install-timings.tsv}"
IMAGE_REGISTRY="${IMAGE_REGISTRY:-ghcr.io/devopssquaddev}"
IMAGE_TAG="${IMAGE_TAG:-dev}"
HELM_RELEASE_NAME="${HELM_RELEASE_NAME:-zelkor-platform}"
GATEWAY_NAMESPACE="${GATEWAY_NAMESPACE:-default}"
# Pinned gVisor point release for kind sandbox bootstrap (see internal/plan/component_compatibility_matrix.md)
GVISOR_RELEASE="${GVISOR_RELEASE:-20260817}"
DOCKER_PLATFORM="${DOCKER_PLATFORM:-$(case "$(uname -m)" in aarch64|arm64) echo linux/arm64 ;; *) echo linux/amd64 ;; esac)}"
# A lost watch is not a failed rollout: re-check real status before giving up.
WAIT_RECHECK_GRACE="${WAIT_RECHECK_GRACE:-90}"
JOB_WAIT_TIMEOUT="${JOB_WAIT_TIMEOUT:-10m}"
# Optional components only warn. Set true to exit non-zero when anything degraded.
INSTALL_STRICT="${INSTALL_STRICT:-false}"
DEGRADED_COMPONENTS=()
NOT_VERIFIED=()

case "$INSTALL_PROFILE" in
  fast)
    VALUES_FILE="${VALUES_FILE:-profiles/values-local-fast.yaml}"
    KIND_CONFIG="${KIND_CONFIG:-kind-config.yaml}"
    INSTALL_EXAMPLES="${INSTALL_EXAMPLES:-true}"
    GVISOR_INSTALL="${GVISOR_INSTALL:-true}"
    RUN_DEMO_TOUR="${RUN_DEMO_TOUR:-true}"
    ;;
  full)
    VALUES_FILE="${VALUES_FILE:-profiles/values-local.yaml}"
    KIND_CONFIG="${KIND_CONFIG:-kind-config.yaml}"
    INSTALL_EXAMPLES="${INSTALL_EXAMPLES:-true}"
    GVISOR_INSTALL="${GVISOR_INSTALL:-true}"
    RUN_DEMO_TOUR="${RUN_DEMO_TOUR:-false}"
    # Upgrade-only: never create kind or run download on full (see require_full_profile_prereqs).
    PREFETCH_IMAGES="${PREFETCH_IMAGES:-false}"
    ;;
  *)
    echo "[install] ERROR: Unknown INSTALL_PROFILE=${INSTALL_PROFILE} (use fast or full)" >&2
    exit 1
    ;;
esac

if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
  C_GREEN=$'\033[32m'
  C_YELLOW=$'\033[33m'
  C_RESET=$'\033[0m'
else
  C_GREEN=''
  C_YELLOW=''
  C_RESET=''
fi

log() {
  local elapsed=$(( $(date +%s) - INSTALL_START_TIME ))
  printf '[install +%02d:%02d] %s\n' $((elapsed / 60)) $((elapsed % 60)) "$*"
}
log_green() { log "${C_GREEN}$*${C_RESET}"; }
log_warn() { log "${C_YELLOW}$*${C_RESET}"; }
die() { log "ERROR: $*"; exit 1; }

mark_degraded() {
  local what="$1"
  local hint="${2:-}"
  DEGRADED_COMPONENTS+=("${what}"$'\t'"${hint}")
  log_warn "WARNING: ${what} is degraded; install continues.${hint:+ Inspect: ${hint}}"
}

inspect_hint() {
  case "$1" in
    "jobs -l "*) echo "kubectl --context ${KCTX} get $1" ;;
    job/*) echo "kubectl --context ${KCTX} logs $1 --tail=50" ;;
    *) echo "kubectl --context ${KCTX} describe $1" ;;
  esac
}

skip_wait() {
  local what="$1"
  local reason="$2"
  NOT_VERIFIED+=("${what}"$'\t'"$(inspect_hint "$what")")
  log "    not waiting: ${what} (${reason})"
}

step_begin() {
  local safe="${1//[^a-zA-Z0-9_]/_}"
  eval "STEP_START_${safe}=\$(date +%s)"
  _ux_hook step_begin "$1"
  log ">> $1"
}

step_end() {
  local step="$1"
  local safe="${step//[^a-zA-Z0-9_]/_}"
  local var="STEP_START_${safe}"
  local start=${!var:-0}
  local s=$(( $(date +%s) - start ))
  _ux_hook step_end "$step" "$s"
  log "<< ${step} (${s}s)"
  printf '%s\t%s\n' "$step" "$s" >> "$INSTALL_TIMINGS_FILE"
}

# Incremental TTFV: skip healthy gateway bootstrap; wait independent rollouts in parallel.
deployment_available() {
  local ns="$1"
  local name="$2"
  local available
  available=$(kubectl --context "$KCTX" get deployment "$name" -n "$ns" \
    -o jsonpath='{.status.conditions[?(@.type=="Available")].status}' 2>/dev/null || true)
  [[ "$available" == "True" ]]
}

# Real status of a rollout/job, independent of whether a watch survived.
resource_healthy() {
  local target="$1"
  local ns="${2:-}"
  local -a args=(--context "$KCTX" get "$target")
  [[ -n "$ns" ]] && args+=(-n "$ns")
  case "${target%%/*}" in
    deployment|deployments|deploy)
      local available
      available=$(kubectl "${args[@]}" \
        -o jsonpath='{.status.conditions[?(@.type=="Available")].status}' 2>/dev/null || true)
      [[ "$available" == "True" ]]
      ;;
    statefulset|statefulsets|sts)
      local ready desired
      ready=$(kubectl "${args[@]}" -o jsonpath='{.status.readyReplicas}' 2>/dev/null || true)
      desired=$(kubectl "${args[@]}" -o jsonpath='{.spec.replicas}' 2>/dev/null || true)
      [[ "${desired:-0}" -gt 0 && "${ready:-0}" -ge "${desired:-0}" ]]
      ;;
    job|jobs)
      local succeeded complete
      succeeded=$(kubectl "${args[@]}" -o jsonpath='{.status.succeeded}' 2>/dev/null || true)
      complete=$(kubectl "${args[@]}" \
        -o jsonpath='{.status.conditions[?(@.type=="Complete")].status}' 2>/dev/null || true)
      [[ "${succeeded:-0}" -ge 1 || "$complete" == "True" ]]
      ;;
    *)
      return 1
      ;;
  esac
}

# Every job matching a selector reports success.
jobs_selector_healthy() {
  local selector="$1"
  local states
  states=$(kubectl --context "$KCTX" get jobs -l "$selector" \
    -o jsonpath='{range .items[*]}{.status.succeeded}{"\n"}{end}' 2>/dev/null || true)
  [[ -n "$states" ]] || return 1
  while IFS= read -r s; do
    [[ "${s:-0}" -ge 1 ]] || return 1
  done <<< "$states"
  return 0
}

# Poll after a timed-out watch; the workload often lands seconds later.
recheck_healthy() {
  local checker="$1"
  shift
  local waited=0
  while true; do
    if "$checker" "$@"; then
      return 0
    fi
    [[ "$waited" -lt "$WAIT_RECHECK_GRACE" ]] || return 1
    sleep 5
    waited=$((waited + 5))
  done
}

# criticality: critical -> die; optional -> record and continue.
handle_wait_failure() {
  local criticality="$1"
  local what="$2"
  local checker="$3"
  shift 3
  log_warn "wait for ${what} did not return cleanly; re-checking actual status (grace ${WAIT_RECHECK_GRACE}s)..."
  if recheck_healthy "$checker" "$@"; then
    log_green "${what} is healthy despite the wait timing out; continuing."
    return 0
  fi
  local hint
  hint=$(inspect_hint "$what")
  if [[ "$criticality" == "critical" ]]; then
    die "${what} is not healthy after ${WAIT_RECHECK_GRACE}s recheck. Inspect: ${hint}"
  fi
  mark_degraded "$what" "$hint"
  return 0
}

wait_one() {
  local criticality="$1"
  local target="$2"
  local ns="${3:-}"
  local -a args=(--context "$KCTX" rollout status "$target" --timeout="$ROLLOUT_WAIT_TIMEOUT")
  [[ -n "$ns" ]] && args+=(-n "$ns")
  _ux_hook wait_one_begin "$target"
  log "    waiting: ${target}${ns:+ (ns ${ns})}"
  if kubectl "${args[@]}"; then
    _ux_hook wait_one_end
    return 0
  fi
  _ux_hook wait_one_end
  handle_wait_failure "$criticality" "$target" resource_healthy "$target" "$ns"
}

wait_group() {
  local criticality="$1"
  local label="$2"
  shift 2
  local pids=()
  local targets=()
  local failed=()
  local t pid i=0
  [[ $# -gt 0 ]] || return 0
  _ux_hook wait_group_begin "$label" "$@"
  log "  -> ${label}"
  for t in "$@"; do
    log "    waiting: ${t}"
    kubectl --context "$KCTX" rollout status "$t" --timeout="$ROLLOUT_WAIT_TIMEOUT" &
    pids+=("$!")
    targets+=("$t")
  done
  for pid in "${pids[@]}"; do
    if ! wait "$pid"; then
      failed+=("${targets[$i]}")
    fi
    i=$((i + 1))
  done
  if [[ ${#failed[@]} -gt 0 ]]; then
    for t in "${failed[@]}"; do
      handle_wait_failure "$criticality" "$t" resource_healthy "$t"
    done
  fi
  _ux_hook wait_group_end
}

wait_job() {
  local criticality="$1"
  local name="$2"
  log "  waiting: job/${name}"
  if kubectl --context "$KCTX" wait --for=condition=complete \
    "job/${name}" --timeout="$JOB_WAIT_TIMEOUT"; then
    return 0
  fi
  handle_wait_failure "$criticality" "job/${name}" resource_healthy "job/${name}"
}

wait_jobs_selector() {
  local criticality="$1"
  local selector="$2"
  log "  waiting: jobs -l ${selector}"
  if kubectl --context "$KCTX" wait --for=condition=complete job -l "$selector" \
    --timeout="$JOB_WAIT_TIMEOUT"; then
    return 0
  fi
  handle_wait_failure "$criticality" "jobs -l ${selector}" jobs_selector_healthy "$selector"
}

wait_langfuse_bootstrap_job() {
  local job="${HELM_RELEASE_NAME}-langfuse-bootstrap"
  if ! kubectl --context "$KCTX" get job "$job" >/dev/null 2>&1; then
    return 0
  fi
  log "  waiting: job/${job}"
  if kubectl --context "$KCTX" wait --for=condition=complete "job/${job}" \
    --timeout="$JOB_WAIT_TIMEOUT"; then
    return 0
  fi
  handle_wait_failure optional "job/${job}" resource_healthy "job/${job}"
}

helm_user_value() {
  local dotted="$1"
  if ! command -v python3 >/dev/null 2>&1; then
    return 0
  fi
  helm get values zelkor-platform --kube-context "$KCTX" -o json 2>/dev/null | python3 -c '
import json, sys
raw = sys.stdin.read().strip()
if not raw:
    raise SystemExit(0)
try:
    data = json.loads(raw)
except json.JSONDecodeError:
    raise SystemExit(0)
cur = data
for part in sys.argv[1].split("."):
    if not isinstance(cur, dict):
        cur = ""
        break
    cur = cur.get(part, "")
if cur is None:
    cur = ""
print(cur)
' "$dotted"
}

helm_install_profile_state() {
  if ! command -v python3 >/dev/null 2>&1; then
    echo "unknown"
    return 0
  fi
  helm get values "$HELM_RELEASE_NAME" --kube-context "$KCTX" -o json 2>/dev/null | python3 -c '
import json, sys
raw = sys.stdin.read().strip()
if not raw:
    raise SystemExit(1)
data = json.loads(raw)
netpol = bool(((data.get("security") or {}).get("networkPolicies") or {}).get("enabled"))
seed = bool((((data.get("langfuse") or {}).get("surfaces") or {}).get("evaluators") or {}).get("seedCode"))
if netpol and seed:
    print("full")
elif not netpol and not seed:
    print("fast")
else:
    print("mixed")
'
}

require_full_profile_prereqs() {
  [[ "$INSTALL_PROFILE" == "full" ]] || return 0
  if ! helm list --kube-context "$KCTX" -q 2>/dev/null | grep -qx "$HELM_RELEASE_NAME"; then
    die "INSTALL_PROFILE=full requires Helm release ${HELM_RELEASE_NAME} from a completed fast install on ${CLUSTER_NAME}."
  fi
  local state=""
  if ! state="$(helm_install_profile_state)"; then
    die "INSTALL_PROFILE=full could not read Helm values for ${HELM_RELEASE_NAME}."
  fi
  case "$state" in
    fast)
      log "Full profile: upgrading fast baseline → NetworkPolicies + Langfuse evaluator seed"
      ;;
    full)
      log "Full profile: re-applying full overlay (already on full baseline)"
      ;;
    mixed)
      die "Cluster has a mixed install profile. Delete kind cluster ${CLUSTER_NAME} and run ./install.sh (fast) before INSTALL_PROFILE=full."
      ;;
    *)
      die "INSTALL_PROFILE=full requires a fast-profile baseline (networkPolicies off, Langfuse evaluators off)."
      ;;
  esac
}

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

# Leftover kind node volumes after `kind delete` can ENOSPC the download phase.
reclaim_unused_docker() {
  echo "[download] reclaiming unused Docker volumes and build cache..."
  docker volume prune -f || true
  docker builder prune -af || true
}

require_docker_free_gb() {
  local need_gb="${INSTALL_MIN_FREE_GB:-8}"
  local warn_gb="${INSTALL_WARN_FREE_GB:-20}"
  local avail_kb avail_gb
  avail_kb=$(df -Pk /var/lib/docker 2>/dev/null | awk 'NR==2 {print $4}')
  if [[ -z "$avail_kb" || ! "$avail_kb" =~ ^[0-9]+$ ]]; then
    log_warn "Could not measure Docker disk free space"
    return 0
  fi
  avail_gb=$((avail_kb / 1024 / 1024))
  if (( avail_gb < need_gb )); then
    die "Need ${need_gb}Gi free for kind download (have ${avail_gb}Gi). Reclaim leftover kind data: docker volume prune -f && docker builder prune -af"
  fi
  if (( avail_gb < warn_gb )); then
    log_warn "Only ${avail_gb}Gi free on Docker disk; download may fail with ENOSPC"
  else
    log "Docker disk: ${avail_gb}Gi free"
  fi
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

FIRST_KIND_CREATE=false
if ! kind get clusters 2>/dev/null | grep -qx "$CLUSTER_NAME"; then
  FIRST_KIND_CREATE=true
fi

if [[ "$INSTALL_PROFILE" == "full" && "$FIRST_KIND_CREATE" == "true" ]]; then
  die "INSTALL_PROFILE=full upgrades an existing fast install on kind cluster ${CLUSTER_NAME}. Run ./install.sh first (default INSTALL_PROFILE=fast)."
fi

# Cold create pulls large images during rollouts (registry mirrors); Langfuse migrations add minutes.
ROLLOUT_WAIT_TIMEOUT="${ROLLOUT_WAIT_TIMEOUT:-$([ "$FIRST_KIND_CREATE" = true ] && echo 15m || echo 5m)}"

download_components() {
  [[ "$PREFETCH_IMAGES" == "true" ]] || return 0
  [[ "$FIRST_KIND_CREATE" == "true" ]] || return 0

  reclaim_unused_docker
  require_docker_free_gb

  local dl_start count
  dl_start=$(date +%s)
  : > "$INSTALL_TIMINGS_FILE"
  mapfile -t _PREFETCH_REFS < <(
    VALUES_FILE="$VALUES_FILE" INSTALL_EXAMPLES="$INSTALL_EXAMPLES" \
      IMAGE_REGISTRY="$IMAGE_REGISTRY" IMAGE_TAG="$IMAGE_TAG" \
      ./scripts/install-images.sh
  )
  count=${#_PREFETCH_REFS[@]}

  cat <<EOF

======================================================================
  Downloading components
======================================================================
  Fetching ${count} container images (${PREFETCH_JOBS:-3} at a time) into local registries.
  This step is a one-time download and is not counted in the install timer.
======================================================================

EOF

  if [[ -n "$KIND_NODE_IMAGE" ]]; then
    if ! docker image inspect "$KIND_NODE_IMAGE" >/dev/null 2>&1; then
      echo "[download] pulling kind node base ${KIND_NODE_IMAGE} (platform=${DOCKER_PLATFORM})..."
      docker pull --platform "$DOCKER_PLATFORM" "$KIND_NODE_IMAGE"
    else
      echo "[download] kind node base already local: ${KIND_NODE_IMAGE}"
    fi
  else
    echo "[download] kind node image: kind CLI default (not pre-pulled)"
  fi

  if [[ "$LOCAL_REGISTRY" == "true" ]]; then
    step_begin download_registry_start
    LOCAL_REGISTRY_DOCKER_NAME="$LOCAL_REGISTRY_DOCKER_NAME" \
      LOCAL_REGISTRY_GHCR_NAME="$LOCAL_REGISTRY_GHCR_NAME" \
      LOCAL_REGISTRY_DOCKER_PORT="$LOCAL_REGISTRY_DOCKER_PORT" \
      LOCAL_REGISTRY_GHCR_PORT="$LOCAL_REGISTRY_GHCR_PORT" \
      LOCAL_REGISTRY_BIND="$LOCAL_REGISTRY_BIND" \
      ./scripts/local-registry.sh start
    step_end download_registry_start

    step_begin download_warm_cache
    VALUES_FILE="$VALUES_FILE" INSTALL_EXAMPLES="$INSTALL_EXAMPLES" \
      IMAGE_REGISTRY="$IMAGE_REGISTRY" IMAGE_TAG="$IMAGE_TAG" \
      DOCKER_PLATFORM="$DOCKER_PLATFORM" \
      LOCAL_REGISTRY_BIND="$LOCAL_REGISTRY_BIND" \
      LOCAL_REGISTRY_DOCKER_PORT="$LOCAL_REGISTRY_DOCKER_PORT" \
      LOCAL_REGISTRY_GHCR_PORT="$LOCAL_REGISTRY_GHCR_PORT" \
      ./scripts/warm-registry-cache.sh
    step_end download_warm_cache
  else
    step_begin download_warm_cache
    VALUES_FILE="$VALUES_FILE" INSTALL_EXAMPLES="$INSTALL_EXAMPLES" \
      IMAGE_REGISTRY="$IMAGE_REGISTRY" IMAGE_TAG="$IMAGE_TAG" \
      DOCKER_PLATFORM="$DOCKER_PLATFORM" \
      ./scripts/prefetch-images.sh --pull-only
    step_end download_warm_cache
  fi

  DOWNLOAD_DURATION=$(( $(date +%s) - dl_start ))
  echo "[download] complete (${DOWNLOAD_DURATION}s). Install timer starts now."
}

download_components
INSTALL_START_TIME=$(date +%s)
[[ -f "$INSTALL_TIMINGS_FILE" ]] || : > "$INSTALL_TIMINGS_FILE"
log "Install profile: ${INSTALL_PROFILE} (values=${VALUES_FILE}, node=${KIND_NODE_IMAGE:-kind-default}, local_registry=${LOCAL_REGISTRY})"

warn_deprecated_kind_load() {
  log_warn "WARNING: kind load is deprecated (PREFETCH_KIND_LOAD / KIND_LOAD_IMAGES / --kind-load). Use pull-through registries (LOCAL_REGISTRY=true default) so kubelet pulls via containerd mirrors."
}

if [[ "$PREFETCH_KIND_LOAD" == "true" ]]; then
  warn_deprecated_kind_load
fi

load_images_into_kind() {
  if [[ "$FIRST_KIND_CREATE" != "true" || "$PREFETCH_KIND_LOAD" != "true" ]]; then
    return 0
  fi
  warn_deprecated_kind_load
  log "Loading prefetched images into kind (kubelet local cache)..."
  VALUES_FILE="$VALUES_FILE" INSTALL_EXAMPLES="$INSTALL_EXAMPLES" \
    IMAGE_REGISTRY="$IMAGE_REGISTRY" IMAGE_TAG="$IMAGE_TAG" \
    DOCKER_PLATFORM="$DOCKER_PLATFORM" \
    KIND_CLUSTER="$CLUSTER_NAME" \
    ./scripts/prefetch-images.sh --load-only --kind-load \
    || log "WARNING: kind load failed; kubelet will pull on demand"
}

install_gvisor_on_kind_node() {
  if [[ "$GVISOR_INSTALL" != "true" ]]; then
    return 0
  fi
  if ! docker inspect "${CLUSTER_NAME}-control-plane" >/dev/null 2>&1; then
    log "WARNING: kind node ${CLUSTER_NAME}-control-plane not found; skipping gVisor install"
    return 0
  fi
  step_begin gvisor_install
  if docker exec "${CLUSTER_NAME}-control-plane" sh -c "
    command -v runsc >/dev/null 2>&1 \
      && runsc --version 2>/dev/null | grep -q '${GVISOR_RELEASE}'
  "; then
    log "gVisor release ${GVISOR_RELEASE} already on kind node; skipping install"
  else
    log "Configuring gVisor (runsc) release ${GVISOR_RELEASE} on kind node..."
    if ! docker exec "${CLUSTER_NAME}-control-plane" sh -c "
      set -e
      ARCH=\$(uname -m)
      case \"\$ARCH\" in
        aarch64|arm64) ARCH=aarch64 ;;
        x86_64|amd64) ARCH=x86_64 ;;
      esac
      BASE=https://storage.googleapis.com/gvisor/releases/release/${GVISOR_RELEASE}/\${ARCH}
      for bin in runsc containerd-shim-runsc-v1; do
        curl -fsSL \"\${BASE}/\${bin}\" -o \"/tmp/\${bin}.new\"
        mv -f \"/tmp/\${bin}.new\" \"/usr/local/bin/\${bin}\"
      done
      chmod a+rx /usr/local/bin/runsc /usr/local/bin/containerd-shim-runsc-v1
    "; then
      log "WARNING: gVisor install failed (sandbox RuntimeClass may not work on this node)"
    fi
  fi
  step_end gvisor_install
}

if [[ "$FIRST_KIND_CREATE" == "true" ]]; then
  step_begin kind_create
  _kind_args=(create cluster --name "$CLUSTER_NAME")
  if [[ -n "$KIND_NODE_IMAGE" ]]; then
    _kind_args+=(--image "$KIND_NODE_IMAGE")
    log "Creating kind cluster: $CLUSTER_NAME (node image: ${KIND_NODE_IMAGE})"
  else
    log "Creating kind cluster: $CLUSTER_NAME (kind default node image)"
  fi
  if [[ -f "$KIND_CONFIG" ]]; then
    _kind_args+=(--config "$KIND_CONFIG")
  fi
  kind "${_kind_args[@]}"
  unset _kind_args
  step_end kind_create

  if [[ "$LOCAL_REGISTRY" == "true" ]]; then
    step_begin registry_connect
    LOCAL_REGISTRY_DOCKER_NAME="$LOCAL_REGISTRY_DOCKER_NAME" \
      LOCAL_REGISTRY_GHCR_NAME="$LOCAL_REGISTRY_GHCR_NAME" \
      ./scripts/local-registry.sh connect
    step_end registry_connect
  fi

  if [[ -n "$SELECTED_OLLAMA_LOCAL_HOST" && "$SELECTED_OLLAMA_LOCAL_HOST" == *"host.docker.internal"* ]]; then
    patch_kind_host_docker_internal
  fi
else
  log "Kind cluster already exists: $CLUSTER_NAME"
  kind export kubeconfig --name "$CLUSTER_NAME"
fi

install_gvisor_on_kind_node

kubectl cluster-info --context "kind-${CLUSTER_NAME}" >/dev/null

load_images_into_kind

if [[ "$BUILD_IMAGES" == "true" ]]; then
  log "Building first-party images (tag ${IMAGE_TAG})..."
  IMAGE_REGISTRY="$IMAGE_REGISTRY" IMAGE_TAG="$IMAGE_TAG" ./scripts/build-images.sh
  KIND_LOAD_IMAGES=true
fi

if [[ "$KIND_LOAD_IMAGES" == "true" ]]; then
  warn_deprecated_kind_load
  log "Loading first-party images into kind cluster ${CLUSTER_NAME}..."
  IMAGE_REGISTRY="$IMAGE_REGISTRY" IMAGE_TAG="$IMAGE_TAG" KIND_CLUSTER="$CLUSTER_NAME" \
    ./scripts/build-images.sh --load-only --kind-load
fi

if [[ ! -f "$VALUES_FILE" ]]; then
  die "Values file not found: $VALUES_FILE"
fi

KCTX="kind-${CLUSTER_NAME}"
require_full_profile_prereqs

step_begin envoy_gateway
log "Bootstrapping Envoy Gateway and Envoy AI Gateway..."
if ! bash "$ZELKOR_REPO_ROOT/scripts/bootstrap-gateway.sh" --kube-context "$KCTX"; then
  die "Gateway bootstrap failed (Envoy Gateway / Envoy AI Gateway)"
fi
step_end envoy_gateway

step_begin ai_gateway
log "Envoy AI Gateway included in gateway bootstrap"
step_end ai_gateway

if [[ "$FIRST_KIND_CREATE" != "true" ]]; then
  for job in langfuse-bootstrap gvisor-verify; do
    if kubectl --context "$KCTX" get job "${HELM_RELEASE_NAME}-${job}" >/dev/null 2>&1; then
      log "Deleting stale ${job} Job (re-run; Job spec is immutable)..."
      kubectl --context "$KCTX" delete job "${HELM_RELEASE_NAME}-${job}" --ignore-not-found
    fi
  done
fi

step_begin platform_helm
log "Applying Platform Helm chart from $CHART_PATH..."
HELM_EXTRA_ARGS=()
if [[ "${GVISOR_INSTALL:-true}" == "true" ]]; then
  # shellcheck disable=SC1090
  eval "$(bash "$ZELKOR_REPO_ROOT/scripts/gvisor-preflight.sh" --kube-context "$KCTX" --output shell)" || true
  HELM_EXTRA_ARGS+=(
    --set "security.sandbox.provisioning.mode=${GVISOR_PROVISIONING_MODE:-daemonset}"
    --set "security.sandbox.createRuntimeClass=${GVISOR_CREATE_RUNTIME_CLASS:-true}"
  )
fi
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
  # Playground needs a custom model id on the Zelkor connection (no baked gpt-4o list).
  HELM_EXTRA_ARGS+=(--set-string "langfuse.surfaces.llmConnection.models[0]=${DEFAULT_LLM_MODEL}")
fi

if [[ "$INSTALL_EXAMPLES" == "true" && -f "$FINSERVE_PLATFORM_OVERLAY" ]]; then
  HELM_EXTRA_ARGS+=(-f "$FINSERVE_PLATFORM_OVERLAY")
  log "Platform overlay: $FINSERVE_PLATFORM_OVERLAY (MCP/Langfuse/NeMo; workers via FinServe sharedRoute)"
fi

peek_internal_gateway_svc() {
  local ns="${ZELKOR_NAMESPACE:-zelkor}"
  local release="${HELM_RELEASE_NAME:-zelkor-platform}"
  local stable="${ns}-${release}-dataplane"
  if kubectl --context "$KCTX" get svc "$stable" -n envoy-gateway-system >/dev/null 2>&1; then
    echo "$stable"
    return 0
  fi
  kubectl --context "$KCTX" get svc -n envoy-gateway-system \
    -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.metadata.labels.gateway\.envoyproxy\.io/owning-gateway-name}{"\n"}{end}' 2>/dev/null \
    | awk -F'\t' '$2 != "" { print $1; exit }' || true
}

append_gateway_url_helm() {
  local url="$1"
  local host="${url#http://}"
  host="${host%%/*}"
  host="${host%%:*}"
  HELM_EXTRA_ARGS+=(
    --set "aiGateway.internalUrl=${url}"
    --set "aiGateway.inClusterService.targetHost=${host}"
    --set "mcp.qdrantMCP.aiGatewayUrl=${url}"
  )
}

# Do not guess envoy-default-<release>-gateway — Envoy appends a hash
# (…-gateway-890d4e31). A guessed name does not resolve.
GATEWAY_INTERNAL_URL=""
PEEKED_SVC=$(peek_internal_gateway_svc)
if [[ -n "$PEEKED_SVC" ]]; then
  GATEWAY_INTERNAL_URL="http://${PEEKED_SVC}.envoy-gateway-system.svc.cluster.local:80/v1"
  log "Using existing Envoy data-plane Service: ${GATEWAY_INTERNAL_URL}"
  append_gateway_url_helm "$GATEWAY_INTERNAL_URL"
fi

if [[ ${#HELM_EXTRA_ARGS[@]} -gt 0 ]]; then
  helm upgrade --install "$HELM_RELEASE_NAME" "$CHART_PATH" \
    --kube-context "$KCTX" \
    -f "$VALUES_FILE" \
    "${HELM_EXTRA_ARGS[@]}"
else
  helm upgrade --install "$HELM_RELEASE_NAME" "$CHART_PATH" \
    --kube-context "$KCTX" \
    -f "$VALUES_FILE"
fi
step_end platform_helm

log "Tracking platform rollout progress..."
step_begin rollout_datastores
# Langfuse consumes Postgres, ClickHouse, and S3; Valkey/Qdrant degrade without aborting.
wait_group critical "[1/5] Databases (PostgreSQL, ClickHouse, SeaweedFS)" \
  statefulset/zelkor-platform-postgresql \
  statefulset/zelkor-platform-clickhouse \
  deployment/zelkor-platform-seaweedfs
skip_wait deployment/zelkor-platform-valkey "Langfuse wait is the real gate"
skip_wait statefulset/zelkor-platform-qdrant "mcp-qdrant wait is the real gate"
step_end rollout_datastores

discover_internal_gateway_url() {
  local svc=""
  for _ in $(seq 1 30); do
    svc=$(peek_internal_gateway_svc)
    if [[ -n "$svc" ]]; then
      echo "http://${svc}.envoy-gateway-system.svc.cluster.local:80/v1"
      return 0
    fi
    sleep 2
  done
  return 1
}

if DISCOVERED_INTERNAL_URL=$(discover_internal_gateway_url); then
  if [[ "$DISCOVERED_INTERNAL_URL" == "$GATEWAY_INTERNAL_URL" ]]; then
    log "aiGateway.internalUrl already ${DISCOVERED_INTERNAL_URL}; skipping second Helm upgrade"
  else
    log "Patching in-cluster AI Gateway URL for platform workloads: ${DISCOVERED_INTERNAL_URL}"
    GATEWAY_INTERNAL_URL="$DISCOVERED_INTERNAL_URL"
    GATEWAY_TARGET_HOST="${GATEWAY_INTERNAL_URL#http://}"
    GATEWAY_TARGET_HOST="${GATEWAY_TARGET_HOST%%/*}"
    GATEWAY_TARGET_HOST="${GATEWAY_TARGET_HOST%%:*}"
    # Do not pass HELM_EXTRA_ARGS: it may still contain a guessed internalUrl
    # that Helm last-wins over these --set values.
    helm upgrade "$HELM_RELEASE_NAME" "$CHART_PATH" \
      --kube-context "$KCTX" \
      --reuse-values \
      --set "aiGateway.internalUrl=${GATEWAY_INTERNAL_URL}" \
      --set "aiGateway.inClusterService.targetHost=${GATEWAY_TARGET_HOST}" \
      --set "mcp.qdrantMCP.aiGatewayUrl=${GATEWAY_INTERNAL_URL}"
  fi
else
  log "WARNING: Envoy data-plane Service not found; NeMo/MCP in-cluster LLM calls may fail until aiGateway.internalUrl is set."
fi

step_begin rollout_langfuse
wait_group critical "[3/5] Observability (Langfuse web + worker)" \
  deployment/zelkor-platform-langfuse \
  deployment/zelkor-platform-langfuse-worker
step_end rollout_langfuse

step_begin rollout_aegra
log "  -> [4/5] Agent Orchestrator (Aegra)..."
wait_one critical deployment/zelkor-platform-aegra
step_end rollout_aegra

MCP_WAIT_TARGETS=()
if kubectl --context "$KCTX" get deployment/zelkor-platform-nemo >/dev/null 2>&1; then
  MCP_WAIT_TARGETS+=(deployment/zelkor-platform-nemo)
fi
if kubectl --context "$KCTX" get deployment/zelkor-platform-mcp-gateway >/dev/null 2>&1; then
  MCP_WAIT_TARGETS+=(
    deployment/zelkor-platform-mcp-gateway
    deployment/zelkor-platform-mcp-postgres
    deployment/zelkor-platform-mcp-qdrant
  )
  if kubectl --context "$KCTX" get deployment/zelkor-platform-mcp-sandbox >/dev/null 2>&1; then
    MCP_WAIT_TARGETS+=(deployment/zelkor-platform-mcp-sandbox)
  fi
  for i in 0 1 2; do
    if kubectl --context "$KCTX" get deployment/zelkor-platform-mcp-sandbox-worker-$i >/dev/null 2>&1; then
      MCP_WAIT_TARGETS+=("deployment/zelkor-platform-mcp-sandbox-worker-$i")
    fi
  done
fi
if [[ ${#MCP_WAIT_TARGETS[@]} -gt 0 ]]; then
  step_begin rollout_mcp_nemo
  wait_group optional "[5/5] Guardrails + native MCP (+ sandbox when enabled)" "${MCP_WAIT_TARGETS[@]}"
  step_end rollout_mcp_nemo
fi

step_begin job_langfuse_bootstrap
wait_langfuse_bootstrap_job
step_end job_langfuse_bootstrap

if [[ "$INSTALL_EXAMPLES" == "true" && -d "$FINSERVE_CHART_PATH" ]]; then
  step_begin finserve_helm
  log "Applying FinServe demo chart from $FINSERVE_CHART_PATH..."
  helm dependency update "$FINSERVE_CHART_PATH" >/dev/null
  FINSERVE_HELM_ARGS=()
  if [[ -n "${DEFAULT_LLM_MODEL:-}" ]]; then
    FINSERVE_HELM_ARGS+=(--set-string "desk.platform.defaultLlmModel=${DEFAULT_LLM_MODEL}")
    FINSERVE_HELM_ARGS+=(--set-string "quant.platform.defaultLlmModel=${DEFAULT_LLM_MODEL}")
    FINSERVE_HELM_ARGS+=(--set-string "coder.platform.defaultLlmModel=${DEFAULT_LLM_MODEL}")
  fi
  helm upgrade --install finserve "$FINSERVE_CHART_PATH" \
    --kube-context "$KCTX" \
    -f "$FINSERVE_VALUES_FILE" \
    "${FINSERVE_HELM_ARGS[@]}"
  step_end finserve_helm

  log "Tracking FinServe demo rollout..."
  step_begin job_finserve_seed
  log "  -> [1/2] Seeding demo portfolio database..."
  wait_jobs_selector optional "app.kubernetes.io/instance=finserve"
  step_end job_finserve_seed
  step_begin rollout_finserve
  wait_group optional "[2/2] FinServe desk + quant + coder" \
    deployment/finserve-desk \
    deployment/finserve-quant \
    deployment/finserve-coder
  step_end rollout_finserve
fi

if [[ "$INSTALL_PROFILE" == "fast" && "$INSTALL_EXAMPLES" == "true" && "$RUN_DEMO_TOUR" == "true" ]]; then
  step_begin demo_tour
  log "Running FinServe showcase e2e smokes (sample Langfuse traces in Zelkor Platform project)..."
  DEMO_TOUR_FAILED=false
  if ! KUBECONTEXT="$KCTX" DEFAULT_LLM_MODEL="${DEFAULT_LLM_MODEL:-}" DEMO_TOUR=1 \
    ./scripts/demo-tour.sh; then
    DEMO_TOUR_FAILED=true
    DEGRADED_COMPONENTS+=("demo tour")
    log_green "WARNING: Demo tour did not pass all checks. Due to LLM use, these tests may fail when the model hallucinates or responds non-deterministically. Install completed successfully."
  fi
  step_end demo_tour
fi

END_TIME=$(date +%s)
INSTALL_DURATION=$((END_TIME - INSTALL_START_TIME))
WALL_DURATION=$((END_TIME - START_TIME))
INSTALL_MINUTES=$((INSTALL_DURATION / 60))
INSTALL_SECONDS=$((INSTALL_DURATION % 60))
WALL_MINUTES=$((WALL_DURATION / 60))
WALL_SECONDS=$((WALL_DURATION % 60))

if [[ "$DOWNLOAD_DURATION" -gt 0 ]]; then
  log "Done. Zelkor Platform deployed on kind cluster: $CLUSTER_NAME (download ${DOWNLOAD_DURATION}s + install ${INSTALL_MINUTES}m ${INSTALL_SECONDS}s / ${INSTALL_DURATION}s; wall ${WALL_MINUTES}m ${WALL_SECONDS}s)"
else
  log "Done. Zelkor Platform deployed on kind cluster: $CLUSTER_NAME (installation took ${INSTALL_MINUTES}m ${INSTALL_SECONDS}s / ${INSTALL_DURATION}s)"
fi
if [[ -s "$INSTALL_TIMINGS_FILE" ]]; then
  log "Step timings (${INSTALL_TIMINGS_FILE}):"
  while IFS=$'\t' read -r step secs; do
    log "  ${step}: ${secs}s"
  done < "$INSTALL_TIMINGS_FILE"
fi

install_print_access_footer() {
local lf_host="${INSTALL_DISPLAY_GATEWAY_LANGFUSE_HOST:-langfuse.localhost}"
local aigw_host="${INSTALL_DISPLAY_GATEWAY_AIGW_HOST:-ai-gateway.localhost}"
local agents_host="${INSTALL_DISPLAY_GATEWAY_AGENTS_HOST:-agents.localhost}"
LF_UI_EMAIL="${INSTALL_DISPLAY_LANGFUSE_ADMIN_EMAIL:-}"
LF_UI_PASSWORD="${INSTALL_DISPLAY_LANGFUSE_ADMIN_PASSWORD:-}"
LF_PUBLIC_KEY="${INSTALL_DISPLAY_LANGFUSE_PUBLIC_KEY:-}"
LF_SECRET_KEY="${INSTALL_DISPLAY_LANGFUSE_SECRET_KEY:-}"
LF_ORG_NAME="${INSTALL_DISPLAY_LANGFUSE_ORG_NAME:-}"
LF_ORG_ID="${INSTALL_DISPLAY_LANGFUSE_ORG_ID:-}"
LF_PROJECT_NAME="${INSTALL_DISPLAY_LANGFUSE_PROJECT_NAME:-}"
LF_PROJECT_ID="${INSTALL_DISPLAY_LANGFUSE_PROJECT_ID:-}"
PG_USER="${INSTALL_DISPLAY_POSTGRES_USER:-zelkor}"
PG_PASS="${INSTALL_DISPLAY_POSTGRES_PASSWORD:-}"
PG_DB="${INSTALL_DISPLAY_POSTGRES_DATABASE:-zelkor}"
AIGW_KEY="${INSTALL_DISPLAY_AI_GATEWAY_CONSUMER_KEY:-}"
if kubectl --context "$KCTX" get secret "${HELM_RELEASE_NAME}-langfuse-admin" -o name &>/dev/null; then
  LF_UI_EMAIL="$(kubectl --context "$KCTX" get secret "${HELM_RELEASE_NAME}-langfuse-admin" -o jsonpath='{.data.email}' 2>/dev/null | base64 -d 2>/dev/null || true)"
  LF_UI_PASSWORD="$(kubectl --context "$KCTX" get secret "${HELM_RELEASE_NAME}-langfuse-admin" -o jsonpath='{.data.password}' 2>/dev/null | base64 -d 2>/dev/null || true)"
fi
cat <<EOF

======================================================================
  Zelkor Platform — Available Web UIs & Endpoints
======================================================================

  Component               Service                     URL
  ----------------------  --------------------------  ---------------------------------
  Langfuse Observability  zelkor-platform-langfuse    http://${lf_host}:8088
  Envoy AI Gateway        ai-gateway-controller       http://${aigw_host}:8088
  Aegra Agent Runtime     zelkor-platform-aegra       http://aegra.localhost:8088/docs
EOF
if [[ "$INSTALL_EXAMPLES" == "true" ]]; then
cat <<EOF
  FinServe Demo (front door) ${agents_host}              http://${agents_host}:8088  X-Graph-ID: finserve-advisor|research|quant|coder
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
    URL:              http://${lf_host}:8088
    User / Password:  ${LF_UI_EMAIL:-<see ${HELM_RELEASE_NAME}-langfuse-admin secret>} / ${LF_UI_PASSWORD:-<see secret>}
    Organization:     ${LF_ORG_NAME:-<org>} (${LF_ORG_ID:-<org-id>})
    Project:          ${LF_PROJECT_NAME:-<project>} (${LF_PROJECT_ID:-<project-id>})
    Public API Key:   ${LF_PUBLIC_KEY:-<see langfuse init keys in profile>}
    Secret API Key:   ${LF_SECRET_KEY:-<see langfuse init keys in profile>}
EOF
cat <<EOF

  [Envoy AI Gateway]
    URL:              http://${aigw_host}:8088/v1/chat/completions
    Bearer Token:     ${AIGW_KEY:-<aiGateway.consumerKey in profile>}
    Tenant Header:    X-Tenant-ID: tenant_a
    LLM Providers:    ${LLM_PROVIDER_SUMMARY}
    Default Model:    ${DEFAULT_LLM_MODEL}
EOF
if [[ "$INSTALL_EXAMPLES" == "true" ]]; then
cat <<EOF

  [FinServe Demo Agent]
    URL:              http://${agents_host}:8088  (Host ${agents_host}; X-Graph-ID: finserve-advisor|research|quant|coder)
    Bearer Tokens:    Authorization: Bearer dev:Bank_Alpha
                      Authorization: Bearer dev:Bank_Beta
EOF
fi
cat <<EOF

  [Aegra Agent Runtime]
    URL:              http://aegra.localhost:8088
    Bearer Token:     Authorization: Bearer dev:tenant_a

  [Databases (Internal Cluster / Port-Forward)]
    PostgreSQL:       postgresql://${PG_USER}:${PG_PASS:-<password>}@localhost:5432/${PG_DB}
    Valkey (Redis):   localhost:6379
    ClickHouse:       http://localhost:8123 (user: default)
    Qdrant:           http://localhost:6333
======================================================================
EOF
}

{
cat <<EOF

======================================================================
  Quick Test Commands (Instant Live Tracing)
======================================================================

  1. Test Envoy AI Gateway (model must match your install provider):
     curl -X POST http://${aigw_host}:8088/v1/chat/completions \\
       -H "Content-Type: application/json" \\
       -H "Authorization: Bearer ${AIGW_KEY:-dev-key}" \\
       -H "X-Tenant-ID: tenant_a" \\
       -d '{"model":"${DEFAULT_LLM_MODEL}","messages":[{"role":"user","content":"Hello from Zelkor!"}]}'
EOF
if [[ "$INSTALL_EXAMPLES" == "true" ]]; then
cat <<EOF

  2. Test FinServe (Host ${agents_host}; X-Graph-ID: finserve-advisor|research|quant|coder):
     curl -X POST http://${agents_host}:8088/threads \\
       -H "Host: ${agents_host}" \\
       -H "Content-Type: application/json" \\
       -H "Authorization: Bearer dev:Bank_Alpha" \\
       -d '{"if_exists":"do_nothing"}'
     curl -X POST http://${agents_host}:8088/runs/wait \\
       -H "Host: ${agents_host}" \\
       -H "Content-Type: application/json" \\
       -H "Authorization: Bearer dev:Bank_Alpha" \\
       -H "X-Graph-ID: finserve-advisor" \\
       -d '{"graph_id":"finserve-advisor","input":{"messages":[{"role":"human","content":"What is my portfolio valuation?"}]}}'
EOF
fi
cat <<EOF

  3. View Traces:
     Agent runs (FinServe demo): Langfuse -> project **Zelkor Platform** -> Traces (name **finserve-advisor**)
     Gateway / playground: same project

======================================================================
EOF
if [[ "${DEMO_TOUR_FAILED:-false}" == "true" ]]; then
cat <<EOF
${C_GREEN}  Demo tour (optional verification)
  ------------------------------------------------------------------
  Some demo tour checks did not pass. Due to LLM use, these tests may
  fail when the model hallucinates or responds non-deterministically.
  The platform install completed successfully.${C_RESET}

======================================================================
EOF
fi
if [[ ${#DEGRADED_COMPONENTS[@]} -gt 0 ]]; then
cat <<EOF
${C_YELLOW}  Degraded components (install continued)
  ------------------------------------------------------------------
EOF
for entry in "${DEGRADED_COMPONENTS[@]}"; do
  component="${entry%%$'\t'*}"
  hint="${entry#*$'\t'}"
  [[ "$hint" == "$entry" ]] && hint=""
  printf '  %s\n' "$component"
  [[ -n "$hint" ]] && printf '      %s\n' "$hint"
done
cat <<EOF
${C_RESET}
======================================================================
EOF
fi
if [[ ${#NOT_VERIFIED[@]} -gt 0 ]]; then
cat <<EOF
  Not verified (fire-and-forget)
  ------------------------------------------------------------------
EOF
for entry in "${NOT_VERIFIED[@]}"; do
  component="${entry%%$'\t'*}"
  hint="${entry#*$'\t'}"
  [[ "$hint" == "$entry" ]] && hint=""
  printf '  %s\n' "$component"
  [[ -n "$hint" ]] && printf '      %s\n' "$hint"
done
cat <<EOF

======================================================================
EOF
fi
if [[ "$DOWNLOAD_DURATION" -gt 0 ]]; then
cat <<EOF
  Component download:  ${DOWNLOAD_DURATION}s (outside install timer)
  Install time:        ${INSTALL_MINUTES}m ${INSTALL_SECONDS}s (${INSTALL_DURATION} seconds)
  Wall clock:          ${WALL_MINUTES}m ${WALL_SECONDS}s (${WALL_DURATION} seconds)
======================================================================
EOF
else
cat <<EOF
  Total Installation Time: ${INSTALL_MINUTES}m ${INSTALL_SECONDS}s (${INSTALL_DURATION} seconds)
======================================================================
EOF
fi
}

if [[ ${#DEGRADED_COMPONENTS[@]} -gt 0 && "$INSTALL_STRICT" == "true" ]]; then
  die "INSTALL_STRICT=true and ${#DEGRADED_COMPONENTS[@]} component(s) degraded."
fi
if [[ "${ZELKOR_UX_WRAPPED:-}" == "true" ]]; then
  return 0
fi
install_print_access_footer
exit 0
