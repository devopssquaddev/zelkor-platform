#!/usr/bin/env bash
# Remove a Zelkor CE Helm release from an existing cluster.
# Does not delete Envoy or operators unless --purge-* and Zelkor owns them.
#
#   ./scripts/uninstall.sh --namespace zelkor-play
#   ./scripts/uninstall.sh --purge-gateway --purge-operators
set -euo pipefail

ZELKOR_REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=lib/cluster-install.sh
source "${ZELKOR_REPO_ROOT}/scripts/lib/cluster-install.sh"
# shellcheck source=lib/bootstrap-ownership.sh
source "${ZELKOR_REPO_ROOT}/scripts/lib/bootstrap-ownership.sh"

cluster_install_init

ENVOY_GATEWAY_VERSION="${ENVOY_GATEWAY_VERSION:-v1.9.1}"
BARMAN_PLUGIN_VERSION="${BARMAN_PLUGIN_VERSION:-0.14.0}"

DELETE_NAMESPACE=0
PURGE_GATEWAY=0
PURGE_OPERATORS=0
PURGE_CERT_MANAGER=0
FORCE_PURGE=0

usage() {
  cat <<'EOF'
Usage: ./scripts/uninstall.sh [OPTIONS]

Remove the Zelkor platform Helm release. Envoy and operators stay unless
you pass --purge-* and Zelkor recorded that it installed them.

Options:
  --namespace NAME           Helm namespace (default: zelkor)
  --release NAME             Helm release (default: zelkor-platform)
  --delete-namespace         Delete the release namespace after helm uninstall
  --purge-gateway            Remove Zelkor-owned Envoy Gateway + AI Gateway
  --purge-operators          Remove Zelkor-owned CNPG, ClickHouse Operator, Barman
                             (never cert-manager)
  --purge-cert-manager       Remove cert-manager only if Zelkor installed it
  --force-purge              Ignore missing ownership (legacy / explicit override)
  --kubeconfig PATH
  --kube-context NAME
  --dry-run                  Print argv; do not apply
  -h, --help

Dry-run ownership override (no cluster):
  ZELKOR_BOOTSTRAP_OWNERSHIP=envoy-gateway,ai-gateway,cnpg
EOF
}

while [[ $# -gt 0 ]]; do
  if cluster_install_try_common "$1" "${2:-}"; then
    shift "$CLUSTER_INSTALL_SHIFT"
    continue
  fi
  case "$1" in
    --delete-namespace) DELETE_NAMESPACE=1; shift ;;
    --purge-gateway) PURGE_GATEWAY=1; shift ;;
    --purge-operators) PURGE_OPERATORS=1; shift ;;
    --purge-cert-manager) PURGE_CERT_MANAGER=1; shift ;;
    --force-purge) FORCE_PURGE=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) cluster_install_die "unknown flag: $1" ;;
  esac
done

cluster_install_need kubectl
cluster_install_need helm
cluster_install_apply_kube_flags

zelkor_uninstall_owns() {
  local key="$1"
  if [[ "$FORCE_PURGE" -eq 1 ]]; then
    return 0
  fi
  zelkor_ownership_owns "$key"
}

zelkor_uninstall_kubectl() {
  local label="$1"
  shift
  local cmd=(kubectl)
  if [[ ${#KUBECTL_ARGS[@]} -gt 0 ]]; then
    cmd+=("${KUBECTL_ARGS[@]}")
  fi
  cmd+=("$@")
  cluster_install_print_or_run "$label" "${cmd[@]}"
}

zelkor_helm_release_exists() {
  local release="$1"
  local ns="$2"
  local cmd=(helm status "$release" --namespace "$ns")
  if [[ ${#HELM_KUBE_ARGS[@]} -gt 0 ]]; then
    cmd+=("${HELM_KUBE_ARGS[@]}")
  fi
  "${cmd[@]}" >/dev/null 2>&1
}

zelkor_uninstall_helm() {
  local release="$1"
  local ns="$2"
  local label="$3"
  if [[ "$CLUSTER_INSTALL_DRY_RUN" -ne 1 ]] && ! zelkor_helm_release_exists "$release" "$ns"; then
    echo "SKIP missing helm release ${release} (${ns})"
    return 0
  fi
  # Helm 3.10+ (docs minimum) has no `uninstall --ignore-not-found` (Helm 3.18+).
  local cmd=(helm uninstall "$release" --namespace "$ns")
  if [[ ${#HELM_KUBE_ARGS[@]} -gt 0 ]]; then
    cmd+=("${HELM_KUBE_ARGS[@]}")
  fi
  cluster_install_print_or_run "$label" "${cmd[@]}"
}

echo "uninstall: release=${CLUSTER_INSTALL_RELEASE} namespace=${CLUSTER_INSTALL_NAMESPACE}"

zelkor_uninstall_helm "$CLUSTER_INSTALL_RELEASE" "$CLUSTER_INSTALL_NAMESPACE" HELM_UNINSTALL

if [[ "$PURGE_GATEWAY" -eq 1 ]]; then
  echo "WARNING: --purge-gateway is cluster-scoped."
  if zelkor_uninstall_owns envoy-gateway; then
    zelkor_uninstall_kubectl PURGE_GATEWAY delete --ignore-not-found \
      -f "https://github.com/envoyproxy/gateway/releases/download/${ENVOY_GATEWAY_VERSION}/install.yaml"
  else
    echo "SKIP_UNOWNED envoy-gateway (not in Zelkor ownership record; use --force-purge to override)"
  fi
  if zelkor_uninstall_owns ai-gateway; then
    zelkor_uninstall_helm aieg envoy-ai-gateway-system PURGE_GATEWAY
    zelkor_uninstall_helm aieg-crd envoy-ai-gateway-system PURGE_GATEWAY
  else
    echo "SKIP_UNOWNED ai-gateway (not in Zelkor ownership record; use --force-purge to override)"
  fi
fi

if [[ "$PURGE_OPERATORS" -eq 1 ]]; then
  echo "WARNING: --purge-operators removes CNPG / ClickHouse Operator / Barman (not cert-manager)."
  if zelkor_uninstall_owns cnpg; then
    zelkor_uninstall_helm cnpg cnpg-system PURGE_OPERATORS
  else
    echo "SKIP_UNOWNED cnpg (not in Zelkor ownership record; use --force-purge to override)"
  fi
  if zelkor_uninstall_owns clickhouse-operator; then
    zelkor_uninstall_helm clickhouse-operator clickhouse-operator PURGE_OPERATORS
  else
    echo "SKIP_UNOWNED clickhouse-operator (not in Zelkor ownership record; use --force-purge to override)"
  fi
  if zelkor_uninstall_owns barman; then
    zelkor_uninstall_kubectl PURGE_OPERATORS delete --ignore-not-found \
      -f "https://github.com/cloudnative-pg/plugin-barman-cloud/releases/download/v${BARMAN_PLUGIN_VERSION#v}/manifest.yaml"
  else
    echo "SKIP_UNOWNED barman (not in Zelkor ownership record; use --force-purge to override)"
  fi
fi

if [[ "$PURGE_CERT_MANAGER" -eq 1 ]]; then
  if zelkor_uninstall_owns cert-manager; then
    zelkor_uninstall_helm cert-manager cert-manager PURGE_CERT_MANAGER
  else
    echo "SKIP_UNOWNED cert-manager (not in Zelkor ownership record; use --force-purge to override)"
  fi
fi

if [[ "$DELETE_NAMESPACE" -eq 1 ]]; then
  zelkor_uninstall_kubectl DELETE_NAMESPACE delete namespace \
    "$CLUSTER_INSTALL_NAMESPACE" --ignore-not-found
fi

if [[ "$CLUSTER_INSTALL_DRY_RUN" -eq 1 ]]; then
  echo "uninstall: dry-run done"
  exit 0
fi

echo "uninstall: done"
