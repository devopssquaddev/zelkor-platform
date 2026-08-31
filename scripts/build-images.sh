#!/usr/bin/env bash
# Build first-party Zelkor images. Optional: push to GHCR, load into kind.
#
# Usage (from repo root):
#   ./scripts/build-images.sh
#   ./scripts/build-images.sh --push
#   ./scripts/build-images.sh --kind-load
#   ./scripts/build-images.sh --push --kind-load
#
# Env:
#   IMAGE_REGISTRY  default ghcr.io/devopssquaddev
#   IMAGE_TAG       default dev
#   KIND_CLUSTER    default zelkor
#   IMAGES          space-separated names (default: all)

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

IMAGE_REGISTRY="${IMAGE_REGISTRY:-ghcr.io/devopssquaddev}"
IMAGE_TAG="${IMAGE_TAG:-dev}"
KIND_CLUSTER="${KIND_CLUSTER:-zelkor}"

PUSH=false
KIND_LOAD=false
LOAD_ONLY=false
for arg in "$@"; do
  case "$arg" in
    --push) PUSH=true ;;
    --kind-load) KIND_LOAD=true ;;
    --load-only) LOAD_ONLY=true ;;
    -h|--help)
      sed -n '2,16p' "$0"
      exit 0
      ;;
    *)
      echo "unknown argument: $arg" >&2
      exit 1
      ;;
  esac
done

ALL_IMAGES=(
  zelkor-aegra
  zelkor-aegra-cli
  zelkor-mcp
  zelkor-sandbox-worker
  zelkor-guardrails
  zelkor-example-finserve
)

dockerfile_for() {
  case "$1" in
    zelkor-aegra) echo images/aegra/Dockerfile ;;
    zelkor-aegra-cli) echo images/aegra-cli/Dockerfile ;;
    zelkor-mcp) echo images/mcp/Dockerfile ;;
    zelkor-sandbox-worker) echo images/sandbox-worker/Dockerfile ;;
    zelkor-guardrails) echo images/guardrails/Dockerfile ;;
    zelkor-example-finserve) echo images/example-finserve/Dockerfile ;;
    *) return 1 ;;
  esac
}

if [[ "$PUSH" == true && "$LOAD_ONLY" == true ]]; then
  echo "[build-images] --push cannot be combined with --load-only" >&2
  exit 1
fi

if [[ -n "${IMAGES:-}" ]]; then
  # shellcheck disable=SC2206
  SELECTED=($IMAGES)
else
  SELECTED=("${ALL_IMAGES[@]}")
fi

BUILT=()
for name in "${SELECTED[@]}"; do
  df="$(dockerfile_for "$name")" || { echo "unknown image: $name" >&2; exit 1; }
  ref="${IMAGE_REGISTRY}/${name}:${IMAGE_TAG}"
  if [[ "$LOAD_ONLY" != true ]]; then
    echo "[build-images] docker build ${ref}"
    docker build -f "$df" -t "$ref" \
      --label "org.opencontainers.image.source=https://github.com/devopssquaddev/zelkor-platform" \
      "$ROOT"
  fi
  BUILT+=("$ref")
done

if [[ "$PUSH" == true ]]; then
  for ref in "${BUILT[@]}"; do
    echo "[build-images] docker push ${ref}"
    docker push "$ref"
  done
fi

if [[ "$KIND_LOAD" == true ]]; then
  command -v kind >/dev/null 2>&1 || { echo "kind not found" >&2; exit 1; }
  for ref in "${BUILT[@]}"; do
    echo "[build-images] kind load ${ref} -> ${KIND_CLUSTER}"
    kind load docker-image "$ref" --name "$KIND_CLUSTER"
  done
fi

echo "[build-images] done: ${BUILT[*]}"
