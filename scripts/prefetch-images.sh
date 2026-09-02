#!/usr/bin/env bash
# Prefetch first-party GHCR images for a cold ./install.sh. Does not build.
# Public chart images (postgres, Langfuse, ClickHouse, Envoy, …) are not
# listed — kind's kubelet pulls those from Docker Hub / Quay on demand.
#
# Usage (from repo root or this script):
#   ./scripts/prefetch-images.sh
#   INSTALL_EXAMPLES=false ./scripts/prefetch-images.sh
#   ./scripts/prefetch-images.sh --kind-load
#   ./scripts/prefetch-images.sh --load-only --kind-load
#
# Env:
#   IMAGE_REGISTRY     default ghcr.io/devopssquaddev
#   IMAGE_TAG          default dev
#   KIND_CLUSTER       default zelkor
#   INSTALL_EXAMPLES   default true (FinServe images)
#   PREFETCH_JOBS      parallel docker pull workers (default 3)

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

IMAGE_REGISTRY="${IMAGE_REGISTRY:-ghcr.io/devopssquaddev}"
IMAGE_TAG="${IMAGE_TAG:-dev}"
KIND_CLUSTER="${KIND_CLUSTER:-zelkor}"
INSTALL_EXAMPLES="${INSTALL_EXAMPLES:-true}"
PREFETCH_JOBS="${PREFETCH_JOBS:-3}"

PULL=true
KIND_LOAD=false
for arg in "$@"; do
  case "$arg" in
    --kind-load) KIND_LOAD=true ;;
    --load-only) PULL=false ;;
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

# First-party images from scripts/build-images.sh (pull, never build).
PLATFORM_FIRST_PARTY=(
  zelkor-aegra
  zelkor-aegra-deep
  zelkor-aegra-cli
  zelkor-mcp
  zelkor-langfuse-seed
  zelkor-sandbox-worker
  zelkor-guardrails
)
EXAMPLE_FIRST_PARTY=(
  zelkor-example-finserve
  zelkor-example-finserve-coder
)

IMAGES=()
add_image() {
  local ref="$1"
  [[ -n "$ref" ]] || return 0
  local i
  for i in "${IMAGES[@]+"${IMAGES[@]}"}"; do
    [[ "$i" == "$ref" ]] && return 0
  done
  IMAGES+=("$ref")
}

for name in "${PLATFORM_FIRST_PARTY[@]}"; do
  add_image "${IMAGE_REGISTRY}/${name}:${IMAGE_TAG}"
done
if [[ "$INSTALL_EXAMPLES" == "true" ]]; then
  for name in "${EXAMPLE_FIRST_PARTY[@]}"; do
    add_image "${IMAGE_REGISTRY}/${name}:${IMAGE_TAG}"
  done
fi

if [[ ${#IMAGES[@]} -eq 0 ]]; then
  echo "[prefetch] ERROR: no images to prefetch" >&2
  exit 1
fi

log "images: ${#IMAGES[@]} first-party (INSTALL_EXAMPLES=${INSTALL_EXAMPLES})"

if [[ "$PULL" == true ]]; then
  log "docker pull (parallel ${PREFETCH_JOBS}, 3 retries)..."
  pull_one() {
    local ref="$1" n
    for n in 1 2 3; do
      if docker pull "$ref"; then
        return 0
      fi
      sleep $((n * 2))
    done
    return 1
  }
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
    echo "[prefetch] ERROR: one or more first-party images are not local" >&2
    exit 1
  fi
  if [[ "$failed" -ne 0 ]]; then
    log "WARNING: some docker pull retries failed; images are already local, continuing"
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
    log "kind load ${ref} -> ${KIND_CLUSTER}"
    if ! kind load docker-image "$ref" --name "$KIND_CLUSTER"; then
      log "WARNING: kind load failed: ${ref}"
      load_failed=1
    fi
  done
  [[ "$load_failed" -eq 0 ]] || exit 1
fi

log "done"
