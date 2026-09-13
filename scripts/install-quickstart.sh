#!/usr/bin/env bash
# Evaluate Zelkor CE on an existing Kubernetes cluster (in-cluster-basic).
# Does not create kind, install FinServe, or apply values-local.yaml.
#
#   OPENAI_API_KEY=sk-... ./scripts/install-quickstart.sh --namespace zelkor-play
set -euo pipefail

ZELKOR_REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=lib/cluster-install.sh
source "${ZELKOR_REPO_ROOT}/scripts/lib/cluster-install.sh"

cluster_install_init

usage() {
  cat <<'EOF'
Usage: ./scripts/install-quickstart.sh [OPTIONS]

Deploy Zelkor Community Edition (evaluation) onto an existing cluster.
Uses profiles/values-quickstart.yaml (in-cluster-basic, no operators).

Options:
  --namespace NAME             Release namespace (default: zelkor)
  --release NAME               Helm release name (default: zelkor-platform)
  --topology greenfield|layered|shared
  --hosts-agents HOST          Default: agents.<namespace>.zelkor.local
  --hosts-langfuse HOST        Default: langfuse.<namespace>.zelkor.local
  --parent-ref-name NAME       Required for --topology shared
  --parent-ref-namespace NS    Required for --topology shared
  --gateway-class NAME         Required for --topology shared
  --install-ai-gateway         Shared topology: install AI Gateway + patch EG
  --image-pull-secret NAME     Optional. CE GHCR images are public.
  --strict                     Fail on preflight warnings
  --kubeconfig PATH
  --kube-context NAME
  --set key=value              Extra Helm --set (repeatable)
  --dry-run                    Print bootstrap + helm argv; do not apply
  -h, --help

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
    -h|--help) usage; exit 0 ;;
    *) cluster_install_die "unknown flag: $1" ;;
  esac
done

if [[ -z "$HOSTS_AGENTS" ]]; then
  HOSTS_AGENTS="agents.${CLUSTER_INSTALL_NAMESPACE}.zelkor.local"
fi
if [[ -z "$HOSTS_LANGFUSE" ]]; then
  HOSTS_LANGFUSE="langfuse.${CLUSTER_INSTALL_NAMESPACE}.zelkor.local"
fi

cluster_install_prepare

echo "install-quickstart: topology=${CLUSTER_INSTALL_TOPOLOGY} namespace=${CLUSTER_INSTALL_NAMESPACE} release=${CLUSTER_INSTALL_RELEASE}"
echo "install-quickstart: LLM providers: ${LLM_PROVIDER_SUMMARY} (DEFAULT_LLM_MODEL=${DEFAULT_LLM_MODEL})"
echo "install-quickstart: hosts agents=${HOSTS_AGENTS} langfuse=${HOSTS_LANGFUSE}"

cluster_install_run_bootstrap_gateway
cluster_install_run_helm "${ZELKOR_REPO_ROOT}/profiles/values-quickstart.yaml"

if [[ "$CLUSTER_INSTALL_DRY_RUN" -eq 1 ]]; then
  echo "install-quickstart: dry-run done"
  exit 0
fi

cluster_install_print_dataplane
cluster_install_wait_langfuse
cluster_install_refresh_surfaces

echo
echo "Zelkor evaluation release is applied."
echo "  helm --namespace ${CLUSTER_INSTALL_NAMESPACE} list"
echo
echo "Configure the CLI:"
ctx_flag=""
if [[ -n "$KUBE_CONTEXT" ]]; then
  ctx_flag=" --kube-context ${KUBE_CONTEXT}"
fi
echo "  pip install -e ${ZELKOR_REPO_ROOT}/cli"
echo "  zelkor env add ${CLUSTER_INSTALL_NAMESPACE}${ctx_flag} --namespace ${CLUSTER_INSTALL_NAMESPACE}"
echo
echo "Langfuse admin (generated if unset):"
echo "  kubectl ${KUBECTL_ARGS[*]:-} -n ${CLUSTER_INSTALL_NAMESPACE} get secret ${CLUSTER_INSTALL_RELEASE}-langfuse-admin -o jsonpath='{.data.email}' | base64 -d; echo"
echo "  kubectl ${KUBECTL_ARGS[*]:-} -n ${CLUSTER_INSTALL_NAMESPACE} get secret ${CLUSTER_INSTALL_RELEASE}-langfuse-admin -o jsonpath='{.data.password}' | base64 -d; echo"
echo
echo "Point DNS or /etc/hosts at the Envoy dataplane for:"
echo "  ${HOSTS_AGENTS}"
echo "  ${HOSTS_LANGFUSE}"
if [[ "$CLUSTER_INSTALL_TOPOLOGY" == "layered" ]]; then
  echo "Layered: forward those Hosts from your ingress to the Envoy ClusterIP (preserve Host)."
else
  echo "Envoy dataplane Services:"
  kubectl "${KUBECTL_ARGS[@]}" get svc -n envoy-gateway-system 2>/dev/null || true
fi
echo "install-quickstart: done"
