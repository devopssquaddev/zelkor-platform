#!/usr/bin/env bash
# Deploy Zelkor CE production (operator-cr + HA) onto an existing Kubernetes cluster.
# Does not create kind, install FinServe, or apply values-local.yaml.
#
#   OPENAI_API_KEY=sk-... ./scripts/install-production.sh \
#     --hosts-agents agents.example.com --hosts-langfuse langfuse.example.com
set -euo pipefail

ZELKOR_REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=lib/cluster-install.sh
source "${ZELKOR_REPO_ROOT}/scripts/lib/cluster-install.sh"

cluster_install_init

SKIP_OPERATORS=0
GENERATE_PASSWORDS=0
TLS_ENABLED=0
CLUSTER_ISSUER=""
SERVICE_MONITOR=0

usage() {
  cat <<'EOF'
Usage: ./scripts/install-production.sh --hosts-agents HOST --hosts-langfuse HOST [OPTIONS]

Deploy Zelkor Community Edition (production) onto an existing cluster.
Uses profiles/values-production.yaml (operator-cr, HA, NetworkPolicies).

Required:
  --hosts-agents HOST
  --hosts-langfuse HOST

Options:
  --namespace NAME             Release namespace (default: zelkor)
  --release NAME               Helm release name (default: zelkor-platform)
  --topology greenfield|layered|shared
  --parent-ref-name NAME       Required for --topology shared
  --parent-ref-namespace NS    Required for --topology shared
  --gateway-class NAME         Required for --topology shared
  --install-ai-gateway         Shared topology: install AI Gateway + patch EG
  --skip-operators             Do not run bootstrap-operators.sh
  --generate-passwords         Generate datastore passwords and print once
  --tls                        Enable Gateway HTTPS
  --cluster-issuer NAME        cert-manager ClusterIssuer (with --tls)
  --service-monitor            Enable Prometheus ServiceMonitors
  --kubeconfig PATH
  --kube-context NAME
  --set key=value              Extra Helm --set (repeatable)
  --dry-run                    Print bootstrap + helm argv; do not apply
  -h, --help

Datastore passwords (or --generate-passwords):
  POSTGRES_PASSWORD, CLICKHOUSE_PASSWORD,
  SEAWEEDFS_ACCESS_KEY, SEAWEEDFS_SECRET_KEY

LLM provider (at least one env):
  OPENAI_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY,
  OLLAMA_API_KEY, OLLAMA_LOCAL_HOST, VLLM_BACKEND_URL
EOF
}

while [[ $# -gt 0 ]]; do
  if cluster_install_try_common "$1" "${2:-}"; then
    shift "$CLUSTER_INSTALL_SHIFT"
    continue
  fi
  case "$1" in
    --skip-operators) SKIP_OPERATORS=1; shift ;;
    --generate-passwords) GENERATE_PASSWORDS=1; shift ;;
    --tls) TLS_ENABLED=1; shift ;;
    --cluster-issuer)
      [[ $# -ge 2 ]] || cluster_install_die "missing value for --cluster-issuer"
      CLUSTER_ISSUER="$2"
      shift 2
      ;;
    --service-monitor) SERVICE_MONITOR=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) cluster_install_die "unknown flag: $1" ;;
  esac
done

if [[ -z "$HOSTS_AGENTS" || -z "$HOSTS_LANGFUSE" ]]; then
  cluster_install_die "--hosts-agents and --hosts-langfuse are required (no .localhost defaults)"
fi
if [[ "$HOSTS_AGENTS" == *.localhost || "$HOSTS_LANGFUSE" == *.localhost ]]; then
  cluster_install_die "production hosts must not use *.localhost"
fi
if [[ "$HOSTS_AGENTS" == *.zelkor.local || "$HOSTS_LANGFUSE" == *.zelkor.local ]]; then
  cluster_install_die "production hosts must not use *.zelkor.local; pass real DNS names"
fi

if [[ "$GENERATE_PASSWORDS" -eq 1 ]]; then
  : "${POSTGRES_PASSWORD:=$(cluster_install_rand_b64)}"
  : "${CLICKHOUSE_PASSWORD:=$(cluster_install_rand_b64)}"
  : "${SEAWEEDFS_ACCESS_KEY:=$(cluster_install_rand_b64)}"
  : "${SEAWEEDFS_SECRET_KEY:=$(cluster_install_rand_b64)}"
fi

[[ -n "${POSTGRES_PASSWORD:-}" ]] || cluster_install_die "POSTGRES_PASSWORD is required (or --generate-passwords)"
[[ -n "${CLICKHOUSE_PASSWORD:-}" ]] || cluster_install_die "CLICKHOUSE_PASSWORD is required (or --generate-passwords)"
[[ -n "${SEAWEEDFS_ACCESS_KEY:-}" ]] || cluster_install_die "SEAWEEDFS_ACCESS_KEY is required (or --generate-passwords)"
[[ -n "${SEAWEEDFS_SECRET_KEY:-}" ]] || cluster_install_die "SEAWEEDFS_SECRET_KEY is required (or --generate-passwords)"

if [[ "$TLS_ENABLED" -eq 1 && -z "$CLUSTER_ISSUER" ]]; then
  cluster_install_die "--tls requires --cluster-issuer"
fi

cluster_install_prepare

CLUSTER_INSTALL_HELM_SETS+=(
  --set "postgresql.auth.password=${POSTGRES_PASSWORD}"
  --set "clickhouse.auth.password=${CLICKHOUSE_PASSWORD}"
  --set "seaweedfs.auth.accessKey=${SEAWEEDFS_ACCESS_KEY}"
  --set "seaweedfs.auth.secretKey=${SEAWEEDFS_SECRET_KEY}"
  --set "langfuse.nextauthUrl=https://${HOSTS_LANGFUSE}"
)
if [[ "$TLS_ENABLED" -eq 1 ]]; then
  CLUSTER_INSTALL_HELM_SETS+=(
    --set "gateway.tls.enabled=true"
    --set "gateway.tls.clusterIssuer=${CLUSTER_ISSUER}"
  )
fi
if [[ "$SERVICE_MONITOR" -eq 1 ]]; then
  CLUSTER_INSTALL_HELM_SETS+=(--set "observability.serviceMonitor.enabled=true")
fi

echo "install-production: topology=${CLUSTER_INSTALL_TOPOLOGY} namespace=${CLUSTER_INSTALL_NAMESPACE} release=${CLUSTER_INSTALL_RELEASE}"
echo "install-production: LLM providers: ${LLM_PROVIDER_SUMMARY} (DEFAULT_LLM_MODEL=${DEFAULT_LLM_MODEL})"
echo "install-production: hosts agents=${HOSTS_AGENTS} langfuse=${HOSTS_LANGFUSE}"

if [[ "$SKIP_OPERATORS" -eq 0 ]]; then
  ops=("${ZELKOR_REPO_ROOT}/scripts/bootstrap-operators.sh")
  if [[ -n "$KUBECONFIG_FILE" ]]; then
    ops+=(--kubeconfig "$KUBECONFIG_FILE")
  fi
  if [[ -n "$KUBE_CONTEXT" ]]; then
    ops+=(--kube-context "$KUBE_CONTEXT")
  fi
  cluster_install_print_or_run BOOTSTRAP_OPERATORS "${ops[@]}"
else
  echo "install-production: skip operators"
fi

cluster_install_run_bootstrap_gateway
cluster_install_run_helm "${ZELKOR_REPO_ROOT}/profiles/values-production.yaml"

if [[ "$CLUSTER_INSTALL_DRY_RUN" -eq 1 ]]; then
  echo "install-production: dry-run done"
  exit 0
fi

if [[ "$GENERATE_PASSWORDS" -eq 1 ]]; then
  echo
  echo "Generated datastore passwords (store these; they are not shown again):"
  echo "  POSTGRES_PASSWORD=${POSTGRES_PASSWORD}"
  echo "  CLICKHOUSE_PASSWORD=${CLICKHOUSE_PASSWORD}"
  echo "  SEAWEEDFS_ACCESS_KEY=${SEAWEEDFS_ACCESS_KEY}"
  echo "  SEAWEEDFS_SECRET_KEY=${SEAWEEDFS_SECRET_KEY}"
fi

echo
echo "Zelkor production release is applied."
echo "  kubectl get cluster,clickhouseinstallation -n ${CLUSTER_INSTALL_NAMESPACE}"
echo
echo "Langfuse admin:"
echo "  kubectl ${KUBECTL_ARGS[*]:-} -n ${CLUSTER_INSTALL_NAMESPACE} get secret ${CLUSTER_INSTALL_RELEASE}-langfuse-admin -o jsonpath='{.data.email}' | base64 -d; echo"
echo "  kubectl ${KUBECTL_ARGS[*]:-} -n ${CLUSTER_INSTALL_NAMESPACE} get secret ${CLUSTER_INSTALL_RELEASE}-langfuse-admin -o jsonpath='{.data.password}' | base64 -d; echo"
echo
ctx_flag=""
if [[ -n "$KUBE_CONTEXT" ]]; then
  ctx_flag=" --kube-context ${KUBE_CONTEXT}"
fi
echo "  zelkor env add production${ctx_flag} --namespace ${CLUSTER_INSTALL_NAMESPACE}"
echo "install-production: done"
