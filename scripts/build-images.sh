#!/usr/bin/env bash
# Build first-party Zelkor images. Optional: push to GHCR.
#
# Usage (from repo root):
#   ./scripts/build-images.sh
#   ./scripts/build-images.sh --push
#   ./scripts/build-images.sh --list        # first-party images, build order (one per line)
#   ./scripts/build-images.sh --list-json   # [{name, dockerfile, base, tier}] for the CI release matrix
#
# Deprecated: --kind-load (use GHCR push + pull-through registries / containerd mirrors).
#
# Release tags (IMAGE_TAG=X.Y.Z) are pushed by CI only (.github/workflows/release.yml, which
# signs them); --push of a semver tag outside GitHub Actions is refused. :dev pushes stay allowed.
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
LIST=""
for arg in "$@"; do
  case "$arg" in
    --push) PUSH=true ;;
    --kind-load) KIND_LOAD=true ;;
    --load-only) LOAD_ONLY=true ;;
    --list) LIST=plain ;;
    --list-json) LIST=json ;;
    -h|--help)
      sed -n '2,22p' "$0"
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
  zelkor-aegra-deep
  zelkor-aegra-cli
  zelkor-mcp
  zelkor-langfuse-seed
  zelkor-sandbox-worker
  zelkor-guardrails
  zelkor-example-finserve
  zelkor-example-finserve-coder
  zelkor-armored-gpt-researcher
  zelkor-sidecar
  zelkor-runtime-pydantic-ai
  zelkor-runtime-crewai
  zelkor-runtime-opencode
)

dockerfile_for() {
  case "$1" in
    zelkor-aegra) echo images/aegra/Dockerfile ;;
    zelkor-aegra-deep) echo images/aegra-deep/Dockerfile ;;
    zelkor-aegra-cli) echo images/aegra-cli/Dockerfile ;;
    zelkor-mcp) echo images/mcp/Dockerfile ;;
    zelkor-langfuse-seed) echo images/langfuse-seed/Dockerfile ;;
    zelkor-sandbox-worker) echo images/sandbox-worker/Dockerfile ;;
    zelkor-guardrails) echo images/guardrails/Dockerfile ;;
    zelkor-example-finserve) echo images/example-finserve/Dockerfile ;;
    zelkor-example-finserve-coder) echo images/example-finserve-coder/Dockerfile ;;
    zelkor-armored-gpt-researcher) echo examples/armored-agents/gpt-researcher/Dockerfile ;;
    zelkor-example-legal-redline) echo images/example-legal-redline/Dockerfile ;;
    zelkor-example-sandbox-python) echo images/example-sandbox-python/Dockerfile ;;
    zelkor-sidecar) echo images/sidecar/Dockerfile ;;
    zelkor-runtime-pydantic-ai) echo images/runtime-pydantic-ai/Dockerfile ;;
    zelkor-runtime-crewai) echo images/runtime-crewai/Dockerfile ;;
    zelkor-runtime-opencode) echo images/runtime-opencode/Dockerfile ;;
    *) return 1 ;;
  esac
}

# First-party base image an image is built FROM (passed as a build arg), or empty.
base_for() {
  case "$1" in
    zelkor-aegra-deep|zelkor-example-finserve|zelkor-example-legal-redline) echo zelkor-aegra ;;
    zelkor-example-finserve-coder|zelkor-armored-gpt-researcher) echo zelkor-aegra-deep ;;
    zelkor-example-sandbox-python) echo zelkor-sandbox-worker ;;
    *) echo "" ;;
  esac
}

base_arg_for() {
  case "$(base_for "$1")" in
    zelkor-aegra) echo ZELKOR_AEGRA_IMAGE ;;
    zelkor-aegra-deep) echo ZELKOR_AEGRA_DEEP_IMAGE ;;
    zelkor-sandbox-worker) echo ZELKOR_SANDBOX_WORKER_IMAGE ;;
    *) echo "" ;;
  esac
}

# Build tier: 0 for images on third-party bases, base tier + 1 otherwise (CI builds tiers in order).
tier_for() {
  local base
  base="$(base_for "$1")"
  if [[ -z "$base" ]]; then echo 0; else echo $(( $(tier_for "$base") + 1 )); fi
}

if [[ "$LIST" == plain ]]; then
  printf '%s\n' "${ALL_IMAGES[@]}"
  exit 0
fi
if [[ "$LIST" == json ]]; then
  sep=""
  printf '['
  for name in "${ALL_IMAGES[@]}"; do
    printf '%s{"name":"%s","dockerfile":"%s","base":"%s","tier":%s}' \
      "$sep" "$name" "$(dockerfile_for "$name")" "$(base_for "$name")" "$(tier_for "$name")"
    sep=","
  done
  printf ']\n'
  exit 0
fi

if [[ "$PUSH" == true && "$IMAGE_TAG" =~ ^v?[0-9]+\.[0-9]+\.[0-9]+ && "${GITHUB_ACTIONS:-}" != true ]]; then
  echo "[build-images] refusing to push ${IMAGE_TAG}: release tags are pushed by CI only (release.yml signs them). Use IMAGE_TAG=dev for laptop pushes." >&2
  exit 1
fi

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
    extra_args=(--label "org.opencontainers.image.version=${IMAGE_TAG}")
    if [[ -n "${GITHUB_SHA:-}" ]]; then
      extra_args+=(--label "org.opencontainers.image.revision=${GITHUB_SHA}")
    fi
    base="$(base_for "$name")"
    if [[ -n "$base" ]]; then
      # BASE_IMAGE_REF (CI) pins the base by digest; otherwise the same tag from the registry.
      extra_args+=(--build-arg "$(base_arg_for "$name")=${BASE_IMAGE_REF:-${IMAGE_REGISTRY}/${base}:${IMAGE_TAG}}")
    fi
    docker build -f "$df" -t "$ref" \
      --label "org.opencontainers.image.source=https://github.com/devopssquaddev/zelkor-platform" \
      "${extra_args[@]}" \
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
  echo "[build-images] WARNING: --kind-load is deprecated; use GHCR push and kubelet pull via registry mirrors" >&2
  command -v kind >/dev/null 2>&1 || { echo "kind not found" >&2; exit 1; }
  for ref in "${BUILT[@]}"; do
    echo "[build-images] kind load ${ref} -> ${KIND_CLUSTER}"
    kind load docker-image "$ref" --name "$KIND_CLUSTER"
  done
fi

echo "[build-images] done: ${BUILT[*]}"
