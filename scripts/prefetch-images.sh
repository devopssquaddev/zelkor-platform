#!/usr/bin/env bash
# Prefetch container images for ./install.sh (escape hatch when LOCAL_REGISTRY=false).
#
# Default install path warms pull-through registries via warm-registry-cache.sh.
# Use this script for direct docker pull + optional kind load:
#
# Usage (from repo root):
#   LOCAL_REGISTRY=false ./install.sh
#   ./scripts/prefetch-images.sh --pull-only
#   ./scripts/prefetch-images.sh --load-only --kind-load
#
# Env:
#   VALUES_FILE        passed to install-images.sh
#   IMAGE_REGISTRY     default ghcr.io/devopssquaddev
#   IMAGE_TAG          default dev
#   INSTALL_EXAMPLES   default true
#   KIND_CLUSTER       default zelkor
#   PREFETCH_JOBS      parallel workers (default 3)
#   DOCKER_PLATFORM    default linux/amd64 or linux/arm64 from uname

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

docker_platform() {
  case "$(uname -m)" in
    aarch64|arm64) echo "linux/arm64" ;;
    *) echo "linux/amd64" ;;
  esac
}

IMAGE_REGISTRY="${IMAGE_REGISTRY:-ghcr.io/devopssquaddev}"
IMAGE_TAG="${IMAGE_TAG:-dev}"
KIND_CLUSTER="${KIND_CLUSTER:-zelkor}"
INSTALL_EXAMPLES="${INSTALL_EXAMPLES:-true}"
PREFETCH_JOBS="${PREFETCH_JOBS:-3}"
VALUES_FILE="${VALUES_FILE:-profiles/values-local-fast.yaml}"
DOCKER_PLATFORM="${DOCKER_PLATFORM:-$(docker_platform)}"

PULL=true
KIND_LOAD=false
for arg in "$@"; do
  case "$arg" in
    --kind-load) KIND_LOAD=true ;;
    --load-only) PULL=false ;;
    --pull-only) PULL=true; KIND_LOAD=false ;;
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

log() { echo "[prefetch] $*"; }

mapfile -t IMAGES < <(
  VALUES_FILE="$VALUES_FILE" INSTALL_EXAMPLES="$INSTALL_EXAMPLES" \
    IMAGE_REGISTRY="$IMAGE_REGISTRY" IMAGE_TAG="$IMAGE_TAG" \
    ./scripts/install-images.sh
)
[[ ${#IMAGES[@]} -gt 0 ]] || { echo "[prefetch] ERROR: no images from install-images.sh" >&2; exit 1; }

log "images: ${#IMAGES[@]} (INSTALL_EXAMPLES=${INSTALL_EXAMPLES}, VALUES_FILE=${VALUES_FILE})"

pull_one() {
  local ref="$1" n
  if docker image inspect "$ref" >/dev/null 2>&1; then
    # Re-pull single-platform so kind load does not hit multi-arch digest gaps.
    docker pull --platform "$DOCKER_PLATFORM" "$ref" >/dev/null 2>&1 || true
    if docker image inspect "$ref" >/dev/null 2>&1; then
      log "skip pull (local): ${ref}"
      return 0
    fi
  fi
  for n in 1 2 3; do
    if docker pull --platform "$DOCKER_PLATFORM" "$ref"; then
      return 0
    fi
    if docker image inspect "$ref" >/dev/null 2>&1; then
      log "using locally cached ${ref} after pull failure"
      return 0
    fi
    sleep $((n * 2))
  done
  return 1
}

kind_load_one() {
  local ref="$1"
  local node="${KIND_CLUSTER}-control-plane"
  # kind load docker-image uses ctr import --all-platforms --digests, which fails when
  # the host only has one platform's layers from a multi-arch index. Import the tar
  # for the single platform we pulled instead.
  docker pull --platform "$DOCKER_PLATFORM" "$ref" >/dev/null 2>&1 || true
  if docker save "$ref" | docker exec --privileged -i "$node" \
    ctr --namespace=k8s.io images import --snapshotter=overlayfs -; then
    return 0
  fi
  log "WARNING: ctr import failed, trying kind load docker-image: ${ref}"
  kind load docker-image "$ref" --name "$KIND_CLUSTER"
}

if [[ "$PULL" == true ]]; then
  log "docker pull (parallel ${PREFETCH_JOBS}, skip-if-local, 3 retries)..."
  export -f pull_one
  failed=0
  if ! printf '%s\n' "${IMAGES[@]}" | xargs -P "$PREFETCH_JOBS" -n 1 bash -c 'pull_one "$1"' _; then
    failed=1
  fi
  missing=0
  for ref in "${IMAGES[@]}"; do
    if ! docker image inspect "$ref" >/dev/null 2>&1; then
      log "missing after pull: ${ref}"
      missing=1
    fi
  done
  if [[ "$missing" -ne 0 ]]; then
    echo "[prefetch] ERROR: one or more images are not local" >&2
    exit 1
  fi
  if [[ "$failed" -ne 0 ]]; then
    log "WARNING: some docker pull retries failed; continuing with local cache"
  fi
fi

if [[ "$KIND_LOAD" == true ]]; then
  command -v kind >/dev/null 2>&1 || { echo "kind not found" >&2; exit 1; }
  if ! kind get clusters 2>/dev/null | grep -qx "$KIND_CLUSTER"; then
    echo "[prefetch] ERROR: kind cluster ${KIND_CLUSTER} not found (create it first)" >&2
    exit 1
  fi
  load_failed=0
  for ref in "${IMAGES[@]}"; do
    if ! docker image inspect "$ref" >/dev/null 2>&1; then
      log "skip kind load (not local): ${ref}"
      continue
    fi
    log "kind load ${ref} -> ${KIND_CLUSTER} (platform=${DOCKER_PLATFORM})"
    if ! kind_load_one "$ref"; then
      log "WARNING: kind load failed: ${ref}"
      load_failed=1
    fi
  done
  [[ "$load_failed" -eq 0 ]] || exit 1
fi

log "done"
