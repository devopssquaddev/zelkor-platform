#!/usr/bin/env bash
# Warm pull-through proxy registries from install-images.sh ref list.
# Pulls through localhost proxy ports, then docker rmi to avoid host duplicate cache.
#
# Usage (from repo root):
#   ./scripts/warm-registry-cache.sh
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

docker_platform() {
  case "$(uname -m)" in
    aarch64|arm64) echo "linux/arm64" ;;
    *) echo "linux/amd64" ;;
  esac
}

VALUES_FILE="${VALUES_FILE:-profiles/values-local-fast.yaml}"
INSTALL_EXAMPLES="${INSTALL_EXAMPLES:-true}"
IMAGE_REGISTRY="${IMAGE_REGISTRY:-ghcr.io/devopssquaddev}"
IMAGE_TAG="${IMAGE_TAG:-dev}"
PREFETCH_JOBS="${PREFETCH_JOBS:-3}"
DOCKER_PLATFORM="${DOCKER_PLATFORM:-$(docker_platform)}"
LOCAL_REGISTRY_BIND="${LOCAL_REGISTRY_BIND:-127.0.0.1}"
LOCAL_REGISTRY_DOCKER_PORT="${LOCAL_REGISTRY_DOCKER_PORT:-5000}"
LOCAL_REGISTRY_GHCR_PORT="${LOCAL_REGISTRY_GHCR_PORT:-5001}"

log() { echo "[download] $*"; }

WARM_TOTAL=0
WARM_COUNT_FILE=""
WARM_LOCK_FILE=""

warm_progress() {
  local ref="$1"
  if [[ -n "$WARM_COUNT_FILE" && -f "$WARM_COUNT_FILE" ]]; then
    local n
    exec 200>"${WARM_LOCK_FILE:-${WARM_COUNT_FILE}.lock}"
    flock -x 200
    read -r n < "$WARM_COUNT_FILE"
    n=$((n + 1))
    echo "$n" > "$WARM_COUNT_FILE"
    flock -u 200
    log "image ${n}/${WARM_TOTAL}: ${ref}"
  else
    log "image: ${ref}"
  fi
}

proxy_path_for_ref() {
  local ref="$1"
  case "$ref" in
    ghcr.io/*)
      ref="${ref#ghcr.io/}"
      printf '%s\n' "${LOCAL_REGISTRY_BIND}:${LOCAL_REGISTRY_GHCR_PORT}/${ref}"
      ;;
    docker.io/*)
      ref="${ref#docker.io/}"
      printf '%s\n' "${LOCAL_REGISTRY_BIND}:${LOCAL_REGISTRY_DOCKER_PORT}/${ref}"
      ;;
    *@sha256:*)
      if [[ "$ref" == */*@sha256:* ]]; then
        printf '%s\n' "${LOCAL_REGISTRY_BIND}:${LOCAL_REGISTRY_DOCKER_PORT}/${ref}"
      else
        printf '%s\n' "${LOCAL_REGISTRY_BIND}:${LOCAL_REGISTRY_DOCKER_PORT}/library/${ref}"
      fi
      ;;
    */*)
      printf '%s\n' "${LOCAL_REGISTRY_BIND}:${LOCAL_REGISTRY_DOCKER_PORT}/${ref}"
      ;;
    *)
      printf '%s\n' "${LOCAL_REGISTRY_BIND}:${LOCAL_REGISTRY_DOCKER_PORT}/library/${ref}"
      ;;
  esac
}

registry_port_for_proxy() {
  local proxy="$1"
  if [[ "$proxy" == *":${LOCAL_REGISTRY_GHCR_PORT}/"* ]]; then
    echo "$LOCAL_REGISTRY_GHCR_PORT"
  else
    echo "$LOCAL_REGISTRY_DOCKER_PORT"
  fi
}

manifest_warm() {
  local proxy="$1"
  local port path repo tag
  port="$(registry_port_for_proxy "$proxy")"
  path="${proxy#*:${port}/}"
  if [[ "$path" == *@sha256:* ]]; then
    repo="${path%@sha256:*}"
    tag="${path#*@}"
    curl -fsS -o /dev/null -H 'Accept: application/vnd.docker.distribution.manifest.v2+json' \
      "http://${LOCAL_REGISTRY_BIND}:${port}/v2/${repo}/manifests/${tag}" 2>/dev/null
    return $?
  fi
  repo="${path%:*}"
  tag="${path##*:}"
  curl -fsS -o /dev/null -H 'Accept: application/vnd.docker.distribution.manifest.v2+json' \
    "http://${LOCAL_REGISTRY_BIND}:${port}/v2/${repo}/manifests/${tag}" 2>/dev/null
}

warm_one() {
  local ref="$1" proxy n
  proxy="$(proxy_path_for_ref "$ref")"
  if manifest_warm "$proxy"; then
    warm_progress "cached: ${ref}"
    return 0
  fi
  warm_progress "$ref"
  for n in 1 2 3; do
    if docker pull --quiet --platform "$DOCKER_PLATFORM" "$proxy" 2>&1; then
      docker rmi "$proxy" >/dev/null 2>&1 || log "WARNING: docker rmi failed: ${proxy}"
      return 0
    fi
    sleep $((n * 2))
  done
  return 1
}

mapfile -t IMAGES < <(
  VALUES_FILE="$VALUES_FILE" INSTALL_EXAMPLES="$INSTALL_EXAMPLES" \
    IMAGE_REGISTRY="$IMAGE_REGISTRY" IMAGE_TAG="$IMAGE_TAG" \
    ./scripts/install-images.sh
)
[[ ${#IMAGES[@]} -gt 0 ]] || { echo "[download] ERROR: no images from install-images.sh" >&2; exit 1; }

WARM_TOTAL=${#IMAGES[@]}
WARM_COUNT_FILE="$(mktemp)"
WARM_LOCK_FILE="${WARM_COUNT_FILE}.lock"
echo 0 > "$WARM_COUNT_FILE"
trap 'rm -f "$WARM_COUNT_FILE" "$WARM_LOCK_FILE"' EXIT

log "Fetching ${WARM_TOTAL} container images (${PREFETCH_JOBS} at a time, platform=${DOCKER_PLATFORM})..."
export -f warm_one proxy_path_for_ref manifest_warm registry_port_for_proxy log warm_progress
export DOCKER_PLATFORM LOCAL_REGISTRY_BIND LOCAL_REGISTRY_DOCKER_PORT LOCAL_REGISTRY_GHCR_PORT WARM_TOTAL WARM_COUNT_FILE WARM_LOCK_FILE
failed=0
if ! printf '%s\n' "${IMAGES[@]}" | xargs -P "$PREFETCH_JOBS" -n 1 bash -c 'warm_one "$1"' _; then
  failed=1
fi
[[ "$failed" -eq 0 ]] || { echo "[download] ERROR: one or more image downloads failed" >&2; exit 1; }
log "all ${WARM_TOTAL} images ready"
