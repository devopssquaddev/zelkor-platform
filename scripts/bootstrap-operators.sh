#!/usr/bin/env bash
# Idempotent Gate B operator bootstrap. Skip a controller when its CRD exists
# or when --skip-* is set. Not called from ./install.sh (Path A stays kind).
# --kubeconfig / --kube-context are optional (non-default kube context).
set -euo pipefail

CNPG_CHART_VERSION="${CNPG_CHART_VERSION:-0.29.0}"
CLICKHOUSE_OPERATOR_VERSION="${CLICKHOUSE_OPERATOR_VERSION:-0.27.3}"
CERT_MANAGER_VERSION="${CERT_MANAGER_VERSION:-v1.21.1}"
BARMAN_PLUGIN_VERSION="${BARMAN_PLUGIN_VERSION:-0.14.0}"

SKIP_CNPG=0
SKIP_CLICKHOUSE=0
SKIP_CERT_MANAGER=0
SKIP_BARMAN=0
KUBECONFIG_FILE=""
KUBE_CONTEXT=""
KUBECTL_ARGS=()
HELM_ARGS=()

usage() {
  cat <<'EOF'
Usage: ./scripts/bootstrap-operators.sh [--skip-cnpg] [--skip-clickhouse] [--skip-cert-manager] [--skip-barman]
         [--kubeconfig PATH] [--kube-context NAME]

Installs CloudNativePG, Altinity ClickHouse Operator, and cert-manager when
their CRDs are missing. Optional Barman Cloud plugin (needs cert-manager).
Does not install ESO or a Valkey operator.

--kubeconfig / --kube-context are optional. Customers run this against their
current context. Pass them only when kubectl/helm must not use the default.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --kubeconfig)
      [[ $# -ge 2 ]] || { echo "missing value for --kubeconfig" >&2; exit 2; }
      KUBECONFIG_FILE="$2"
      shift
      ;;
    --kube-context)
      [[ $# -ge 2 ]] || { echo "missing value for --kube-context" >&2; exit 2; }
      KUBE_CONTEXT="$2"
      shift
      ;;
    --skip-cnpg) SKIP_CNPG=1 ;;
    --skip-clickhouse) SKIP_CLICKHOUSE=1 ;;
    --skip-cert-manager) SKIP_CERT_MANAGER=1 ;;
    --skip-barman) SKIP_BARMAN=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown flag: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

need() {
  command -v "$1" >/dev/null 2>&1 || { echo "missing required command: $1" >&2; exit 1; }
}
need kubectl
need helm

if [[ -n "$KUBECONFIG_FILE" ]]; then
  KUBECTL_ARGS+=(--kubeconfig "$KUBECONFIG_FILE")
  HELM_ARGS+=(--kubeconfig "$KUBECONFIG_FILE")
fi
if [[ -n "$KUBE_CONTEXT" ]]; then
  KUBECTL_ARGS+=(--context "$KUBE_CONTEXT")
  HELM_ARGS+=(--kube-context "$KUBE_CONTEXT")
fi

crd_exists() {
  kubectl "${KUBECTL_ARGS[@]}" get crd "$1" >/dev/null 2>&1
}

if [[ "$SKIP_CNPG" -eq 0 ]] && crd_exists clusters.postgresql.cnpg.io; then
  echo "skip CNPG: CRD clusters.postgresql.cnpg.io already exists"
  SKIP_CNPG=1
fi
if [[ "$SKIP_CLICKHOUSE" -eq 0 ]] && crd_exists clickhouseinstallations.clickhouse.altinity.com; then
  echo "skip ClickHouse operator: CRD already exists"
  SKIP_CLICKHOUSE=1
fi
if [[ "$SKIP_CERT_MANAGER" -eq 0 ]] && crd_exists certificates.cert-manager.io; then
  echo "skip cert-manager: CRD certificates.cert-manager.io already exists"
  SKIP_CERT_MANAGER=1
fi

if [[ "$SKIP_CNPG" -eq 0 ]]; then
  helm repo add cnpg https://cloudnative-pg.github.io/charts --force-update
  helm upgrade --install cnpg cnpg/cloudnative-pg \
    "${HELM_ARGS[@]}" \
    --namespace cnpg-system --create-namespace \
    --version "$CNPG_CHART_VERSION" \
    --wait --timeout 5m
fi

if [[ "$SKIP_CLICKHOUSE" -eq 0 ]]; then
  helm repo add clickhouse-operator https://docs.altinity.com/clickhouse-operator --force-update
  helm upgrade --install clickhouse-operator clickhouse-operator/altinity-clickhouse-operator \
    "${HELM_ARGS[@]}" \
    --namespace clickhouse-operator --create-namespace \
    --version "$CLICKHOUSE_OPERATOR_VERSION" \
    --set 'watchNamespaces[0]=.*' \
    --wait --timeout 5m
fi

if [[ "$SKIP_CERT_MANAGER" -eq 0 ]]; then
  helm upgrade --install cert-manager oci://quay.io/jetstack/charts/cert-manager \
    "${HELM_ARGS[@]}" \
    --namespace cert-manager --create-namespace \
    --version "$CERT_MANAGER_VERSION" \
    --set crds.enabled=true \
    --wait --timeout 5m
fi

if [[ "$SKIP_BARMAN" -eq 0 ]]; then
  if ! crd_exists certificates.cert-manager.io; then
    echo "skip Barman plugin: cert-manager CRD missing (install cert-manager or omit --skip-cert-manager)"
  elif crd_exists objectstores.barmancloud.cnpg.io; then
    echo "skip Barman plugin: CRD objectstores.barmancloud.cnpg.io already exists"
  else
    kubectl "${KUBECTL_ARGS[@]}" apply -f "https://github.com/cloudnative-pg/plugin-barman-cloud/releases/download/v${BARMAN_PLUGIN_VERSION#v}/manifest.yaml"
  fi
fi

echo "bootstrap-operators: done"
