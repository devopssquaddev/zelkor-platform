#!/usr/bin/env bash
# Zelkor Platform — local bootstrap (Base Tier)
# Deploys a production-like kind cluster with the unified Helm chart.
#
# Usage:
#   ./install.sh
#
# Prerequisites: docker, kind, helm, kubectl

set -euo pipefail

CLUSTER_NAME="${CLUSTER_NAME:-zelkor}"
CHART_PATH="${CHART_PATH:-charts/zelkor-platform}"
VALUES_FILE="${VALUES_FILE:-${CHART_PATH}/values-local.yaml}"

log() { echo "[install] $*"; }
die() { echo "[install] ERROR: $*" >&2; exit 1; }

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Missing prerequisite: $1"
}

log "Checking prerequisites..."
require_cmd docker
require_cmd kind
require_cmd helm
require_cmd kubectl

if ! docker info >/dev/null 2>&1; then
  die "Docker is not running. Start Docker and retry."
fi

if ! kind get clusters 2>/dev/null | grep -qx "$CLUSTER_NAME"; then
  log "Creating kind cluster: $CLUSTER_NAME"
  kind create cluster --name "$CLUSTER_NAME"
else
  log "Kind cluster already exists: $CLUSTER_NAME"
fi

kubectl cluster-info --context "kind-${CLUSTER_NAME}" >/dev/null

if [[ ! -f "$VALUES_FILE" ]]; then
  die "Values file not found: $VALUES_FILE"
fi

log "Deploying Helm chart from $CHART_PATH"
helm upgrade --install zelkor-platform "$CHART_PATH" \
  --kube-context "kind-${CLUSTER_NAME}" \
  -f "$VALUES_FILE" \
  --wait --timeout 10m

log "Done. Zelkor Platform is deployed on kind cluster: $CLUSTER_NAME"
