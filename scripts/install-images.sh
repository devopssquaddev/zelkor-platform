#!/usr/bin/env bash
# Definitive container image ref list for ./install.sh download / prefetch.
#
# Usage (from repo root):
#   ./scripts/install-images.sh              # stdout: sorted unique refs
#   ./scripts/install-images.sh --sha256     # sha256 of sorted ref list
#   ./scripts/install-images.sh --verify     # diff chart-derived vs bootstrap manifest
#   ./scripts/install-images.sh --capture    # bootstrap refs from live kind node
#
# Env:
#   VALUES_FILE        default profiles/values-local-fast.yaml
#   INSTALL_EXAMPLES   default true
#   IMAGE_REGISTRY     default ghcr.io/devopssquaddev
#   IMAGE_TAG          default dev
#   KIND_CLUSTER       default zelkor (for --capture)
#   KIND_NODE_IMAGE    base node (for --capture subtraction)

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VALUES_FILE="${VALUES_FILE:-profiles/values-local-fast.yaml}"
INSTALL_EXAMPLES="${INSTALL_EXAMPLES:-true}"
IMAGE_REGISTRY="${IMAGE_REGISTRY:-ghcr.io/devopssquaddev}"
IMAGE_TAG="${IMAGE_TAG:-dev}"
KIND_CLUSTER="${KIND_CLUSTER:-zelkor}"
KIND_NODE_IMAGE="${KIND_NODE_IMAGE:-kindest/node:v1.32.2}"
BOOTSTRAP_FILE="${BOOTSTRAP_FILE:-images/install/bootstrap-images.txt}"
FINSERVE_CHART="${FINSERVE_CHART:-examples/finserve/chart}"
FINSERVE_OVERLAY="${FINSERVE_OVERLAY:-examples/finserve/chart/values-platform-overlay.yaml}"

MODE=list
for arg in "$@"; do
  case "$arg" in
    --sha256) MODE=sha256 ;;
    --verify) MODE=verify ;;
    --capture) MODE=capture ;;
    -h|--help)
      sed -n '2,20p' "$0"
      exit 0
      ;;
    *)
      echo "unknown argument: $arg" >&2
      exit 1
      ;;
  esac
done

log() { echo "[install-images] $*" >&2; }

normalize_ref() {
  local ref="$1"
  [[ -n "$ref" ]] || return 0
  ref="${ref#\"}"
  ref="${ref%\"}"
  ref="${ref//\'/}"
  case "$ref" in
    busybox:*|postgres:*|alpine:*|python:*)
      ref="docker.io/library/${ref}"
      ;;
    */*)
      case "$ref" in
        docker.io/*|ghcr.io/*|registry.k8s.io/*|quay.io/*|gcr.io/*) ;;
        *@sha256:*|*:*)
          if [[ "$ref" != */*/* ]]; then
            ref="docker.io/${ref}"
          fi
          ;;
      esac
      ;;
  esac
  if [[ "$ref" == docker.io/* ]] && [[ "$ref" != docker.io/*/* ]]; then
    ref="${ref/docker.io\//docker.io/library/}"
  fi
  printf '%s' "$ref"
}

add_ref() {
  local ref="$1"
  ref="$(normalize_ref "$ref")"
  [[ -n "$ref" ]] || return 0
  local existing
  for existing in "${REFS[@]+"${REFS[@]}"}"; do
    [[ "$existing" == "$ref" ]] && return 0
  done
  REFS+=("$ref")
}

extract_helm_images() {
  local release="$1" chart="$2"
  shift 2
  helm template "$release" "$chart" "$@" 2>/dev/null \
    | awk '/^[[:space:]]*image:[[:space:]]/ {
        sub(/^[[:space:]]*image:[[:space:]]*/, "")
        gsub(/"/, "")
        gsub(/'\''/, "")
        if ($0 != "" && $0 !~ /^\{\{/) print $0
      }'
}

chart_refs() {
  REFS=()
  local platform_args=(-f "$VALUES_FILE")
  if [[ "$INSTALL_EXAMPLES" == "true" && -f "$FINSERVE_OVERLAY" ]]; then
    platform_args+=(-f "$FINSERVE_OVERLAY")
  fi
  local line
  while IFS= read -r line; do
    add_ref "$line"
  done < <(extract_helm_images zelkor charts/zelkor-platform "${platform_args[@]}")

  if [[ "$INSTALL_EXAMPLES" == "true" && -d "$FINSERVE_CHART" ]]; then
    if [[ ! -d "$FINSERVE_CHART/charts" ]]; then
      helm dependency update "$FINSERVE_CHART" >/dev/null 2>&1 || true
    fi
    while IFS= read -r line; do
      add_ref "$line"
    done < <(extract_helm_images finserve "$FINSERVE_CHART" -f "$FINSERVE_CHART/values-local.yaml")
  fi

  local i
  for i in "${!REFS[@]}"; do
    if [[ "${REFS[$i]}" == ghcr.io/devopssquaddev/zelkor-* ]]; then
      local name="${REFS[$i]#ghcr.io/devopssquaddev/}"
      name="${name%%:*}"
      REFS[$i]="${IMAGE_REGISTRY}/${name}:${IMAGE_TAG}"
    fi
  done

  if [[ -f "$BOOTSTRAP_FILE" ]]; then
    while IFS= read -r line || [[ -n "$line" ]]; do
      line="${line%%#*}"
      line="$(echo "$line" | xargs 2>/dev/null || true)"
      [[ -n "$line" ]] && add_ref "$line"
    done <"$BOOTSTRAP_FILE"
  fi

  printf '%s\n' "${REFS[@]}" | sort -u
}

refs_sha256() {
  chart_refs | sha256sum | awk '{print $1}'
}

capture_bootstrap_refs() {
  command -v docker >/dev/null 2>&1 || { log "docker required"; exit 1; }
  local node="${KIND_CLUSTER}-control-plane"
  docker inspect "$node" >/dev/null 2>&1 || { log "kind node ${node} not found"; exit 1; }

  local base_refs=()
  if docker image inspect "$KIND_NODE_IMAGE" >/dev/null 2>&1; then
    cid="$(docker run -d --privileged --entrypoint /bin/sleep "$KIND_NODE_IMAGE" infinity)"
    docker exec "$cid" ctr -n k8s.io images ls -q 2>/dev/null | sort -u > /tmp/zelkor-base-images.$$ || true
    docker rm -f "$cid" >/dev/null 2>&1 || true
    mapfile -t base_refs < /tmp/zelkor-base-images.$$
    rm -f /tmp/zelkor-base-images.$$
  fi

  mapfile -t all_refs < <(docker exec "$node" ctr -n k8s.io images ls -q 2>/dev/null | sort -u)
  local ref
  for ref in "${all_refs[@]}"; do
    [[ -n "$ref" ]] || continue
    case "$ref" in
      registry.k8s.io/*|docker.io/kindest/*) continue ;;
    esac
    local skip=false
    local base
    for base in "${base_refs[@]}"; do
      [[ "$ref" == "$base" ]] && skip=true && break
    done
    [[ "$skip" == true ]] && continue
    case "$ref" in
      docker.io/envoyproxy/*|ghcr.io/devopssquaddev/zelkor-*|docker.io/langfuse/*|docker.io/library/*|docker.io/postgres*|docker.io/valkey/*|docker.io/clickhouse/*|docker.io/qdrant/*|docker.io/chrislusf/*|ghcr.io/shyim/*|docker.io/alpine*)
        echo "$ref"
        ;;
    esac
  done | sort -u
}

verify_refs() {
  mapfile -t expected < <(chart_refs)
  mapfile -t bootstrap < <(grep -v '^#' "$BOOTSTRAP_FILE" | grep -v '^[[:space:]]*$' | sort -u || true)
  local missing=0
  local ref
  for ref in "${bootstrap[@]}"; do
    ref="$(normalize_ref "$ref")"
    if ! printf '%s\n' "${expected[@]}" | grep -Fxq "$ref"; then
      log "bootstrap not in chart-derived set: $ref"
      missing=1
    fi
  done
  [[ "$missing" -eq 0 ]] || exit 1
  log "verify OK (${#expected[@]} refs)"
}

case "$MODE" in
  list) chart_refs ;;
  sha256) refs_sha256 ;;
  verify) verify_refs ;;
  capture) capture_bootstrap_refs ;;
esac
