#!/usr/bin/env bash
# Re-run the chart's {release}-langfuse-surfaces Job (zelkor-langfuse-seed image).
# First platform Helm pass often runs before Langfuse/MCP/consumerKey are ready.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CHART="${CHART_PATH:-$ROOT/charts/zelkor-platform}"
RELEASE="${HELM_RELEASE_NAME:-zelkor-platform}"
NS="${ZELKOR_NAMESPACE:-zelkor}"
WAIT="${LANGFUSE_SURFACES_WAIT:-true}"
WAIT_TIMEOUT="${LANGFUSE_SURFACES_WAIT_TIMEOUT:-5m}"

KUBECTL=(kubectl)
HELM=(helm)

usage() {
  cat <<'EOF'
Usage: ./scripts/refresh-langfuse-surfaces.sh [--kubeconfig PATH] [--kube-context NAME]
       [--namespace NS] [--release NAME] [--no-wait]

Deletes and recreates the Helm-managed langfuse-surfaces Job so Playground gets
the LLM connection (zelkor-ai-gateway + customModels) and MCP saved tools.
Requires langfuse.init.enabled and langfuse.surfaces knobs in release values.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --kubeconfig)
      KUBECTL+=(--kubeconfig "$2")
      HELM+=(--kubeconfig "$2")
      shift 2
      ;;
    --kube-context)
      KUBECTL+=(--context "$2")
      HELM+=(--kube-context "$2")
      shift 2
      ;;
    --namespace)
      NS="$2"
      shift 2
      ;;
    --release)
      RELEASE="$2"
      shift 2
      ;;
    --no-wait)
      WAIT=false
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "refresh-langfuse-surfaces: unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

log() { printf '%s\n' "$*"; }

if ! "${HELM[@]}" get manifest "$RELEASE" -n "$NS" 2>/dev/null \
  | grep -q "${RELEASE}-langfuse-surfaces"; then
  log "refresh-langfuse-surfaces: skip (Job not in manifest; enable langfuse.init + surfaces)"
  exit 0
fi

log "refresh-langfuse-surfaces: re-run ${RELEASE}-langfuse-surfaces Job"
"${KUBECTL[@]}" -n "$NS" delete job "${RELEASE}-langfuse-surfaces" --ignore-not-found
"${HELM[@]}" upgrade "$RELEASE" "$CHART" \
  --namespace "$NS" \
  --reuse-values \
  --timeout 10m \
  --wait=false

if [[ "$WAIT" != "true" ]]; then
  exit 0
fi

if "${KUBECTL[@]}" -n "$NS" get job "${RELEASE}-langfuse-surfaces" >/dev/null 2>&1; then
  "${KUBECTL[@]}" -n "$NS" wait --for=condition=complete "job/${RELEASE}-langfuse-surfaces" --timeout="$WAIT_TIMEOUT" || {
    log "refresh-langfuse-surfaces: Job did not complete (check logs job/${RELEASE}-langfuse-surfaces)"
    exit 1
  }
fi
