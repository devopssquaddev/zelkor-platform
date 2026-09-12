#!/usr/bin/env bash
# Re-run chart seed Jobs (langfuse-admin + langfuse-surfaces). First platform Helm
# creates them before Langfuse is Ready; Jobs are not Helm hooks.
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

Deletes and recreates Helm-managed langfuse-admin and langfuse-surfaces Jobs after
Langfuse is up. Surfaces seeds Playground (zelkor-ai-gateway + customModels + MCP
tools). Admin signs up the first user when langfuse.admin.enabled.
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

wait_job() {
  local name="$1"
  if ! "${KUBECTL[@]}" -n "$NS" get job "$name" >/dev/null 2>&1; then
    return 0
  fi
  "${KUBECTL[@]}" -n "$NS" wait --for=condition=complete "job/${name}" --timeout="$WAIT_TIMEOUT" || {
    log "refresh-langfuse-surfaces: Job did not complete (check logs job/${name})"
    return 1
  }
}

HAS_SURFACES=false
HAS_ADMIN=false
if MANIFEST="$("${HELM[@]}" get manifest "$RELEASE" -n "$NS")"; then
  # Here-string: `grep -q` + pipefail + a pipe SIGPIPEs printf on an early match.
  if grep -Fq "${RELEASE}-langfuse-surfaces" <<<"$MANIFEST"; then
    HAS_SURFACES=true
  fi
  if grep -Fq "${RELEASE}-langfuse-admin" <<<"$MANIFEST"; then
    HAS_ADMIN=true
  fi
else
  log "refresh-langfuse-surfaces: helm get manifest failed; falling back to live Jobs"
fi
if [[ "$HAS_SURFACES" != "true" ]] && "${KUBECTL[@]}" -n "$NS" get job "${RELEASE}-langfuse-surfaces" >/dev/null 2>&1; then
  HAS_SURFACES=true
fi
if [[ "$HAS_ADMIN" != "true" ]] && "${KUBECTL[@]}" -n "$NS" get job "${RELEASE}-langfuse-admin" >/dev/null 2>&1; then
  HAS_ADMIN=true
fi

if [[ "$HAS_SURFACES" != "true" && "$HAS_ADMIN" != "true" ]]; then
  log "refresh-langfuse-surfaces: skip (no admin/surfaces Job in manifest or cluster)"
  exit 0
fi

log "refresh-langfuse-surfaces: re-run seed Jobs (admin=${HAS_ADMIN} surfaces=${HAS_SURFACES})"
if [[ "$HAS_SURFACES" == "true" ]]; then
  "${KUBECTL[@]}" -n "$NS" delete job "${RELEASE}-langfuse-surfaces" --ignore-not-found
fi
if [[ "$HAS_ADMIN" == "true" ]]; then
  "${KUBECTL[@]}" -n "$NS" delete job "${RELEASE}-langfuse-admin" --ignore-not-found
fi
"${HELM[@]}" upgrade "$RELEASE" "$CHART" \
  --namespace "$NS" \
  --reuse-values \
  --timeout 10m \
  --wait=false

if [[ "$WAIT" != "true" ]]; then
  exit 0
fi

failed=0
if [[ "$HAS_ADMIN" == "true" ]]; then
  wait_job "${RELEASE}-langfuse-admin" || failed=1
fi
if [[ "$HAS_SURFACES" == "true" ]]; then
  wait_job "${RELEASE}-langfuse-surfaces" || failed=1
fi
exit "$failed"
