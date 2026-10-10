#!/usr/bin/env bash
# Resolve gVisor provisioning mode before Helm (auto -> daemonset | preinstalled | none).
# daemonset (install runsc and restart the node runtime) only when GVISOR_INSTALL_OPT_IN=true.
set -euo pipefail

KUBECTL=(kubectl)
FAIL_CLOSED="${GVISOR_FAIL_CLOSED:-false}"
OUTPUT_FORMAT="${GVISOR_PREFLIGHT_OUTPUT:-shell}"
OPT_IN="${GVISOR_INSTALL_OPT_IN:-false}"

usage() {
  cat <<'EOF'
Usage: ./scripts/gvisor-preflight.sh [--kubeconfig PATH] [--kube-context NAME]
       [--fail-closed] [--output shell|helm]

Exports GVISOR_PROVISIONING_MODE and GVISOR_CREATE_RUNTIME_CLASS, or prints --set flags.
A working RuntimeClass resolves to preinstalled. containerd alone resolves to daemonset
only when GVISOR_INSTALL_OPT_IN=true. Otherwise the mode is none.
Helm chart mode=auto does not install runsc when preflight is skipped.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --kubeconfig)
      KUBECTL+=(--kubeconfig "$2")
      shift 2
      ;;
    --kube-context)
      KUBECTL+=(--context "$2")
      shift 2
      ;;
    --fail-closed)
      FAIL_CLOSED=true
      shift
      ;;
    --output)
      OUTPUT_FORMAT="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown flag: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

log() { printf 'gvisor-preflight: %s\n' "$*" >&2; }

# Helm deletes a RuntimeClass it rendered if the next upgrade sets createRuntimeClass=false.
# An existing class this release does not own must stay false so install does not adopt it.
gvisor_runtimeclass_owned_by_release() {
  local rel ns
  [[ -n "${GVISOR_HELM_RELEASE:-}" && -n "${GVISOR_HELM_NAMESPACE:-}" ]] || return 1
  rel="$("${KUBECTL[@]}" get runtimeclass gvisor \
    -o jsonpath='{.metadata.annotations.meta\.helm\.sh/release-name}' 2>/dev/null || true)"
  ns="$("${KUBECTL[@]}" get runtimeclass gvisor \
    -o jsonpath='{.metadata.annotations.meta\.helm\.sh/release-namespace}' 2>/dev/null || true)"
  [[ "$rel" == "$GVISOR_HELM_RELEASE" && "$ns" == "$GVISOR_HELM_NAMESPACE" ]]
}

warn_or_fail() {
  log "$1"
  if [[ "$FAIL_CLOSED" == "true" ]]; then
    exit 1
  fi
}

smoke_gvisor() {
  "${KUBECTL[@]}" delete pod zelkor-gvisor-preflight-smoke --ignore-not-found --wait=false >/dev/null 2>&1 || true
  "${KUBECTL[@]}" apply -f - >&2 <<'EOF'
apiVersion: v1
kind: Pod
metadata:
  name: zelkor-gvisor-preflight-smoke
  namespace: default
spec:
  runtimeClassName: gvisor
  restartPolicy: Never
  tolerations:
    - operator: Exists
  containers:
    - name: smoke
      image: busybox:1.38.0
      command: ["dmesg"]
EOF
  local deadline=$((SECONDS + 90))
  while (( SECONDS < deadline )); do
    local phase="$("${KUBECTL[@]}" get pod zelkor-gvisor-preflight-smoke -o jsonpath='{.status.phase}' 2>/dev/null || true)"
    if [[ "${phase}" == "Succeeded" ]]; then
      "${KUBECTL[@]}" delete pod zelkor-gvisor-preflight-smoke --wait=false >/dev/null 2>&1 || true
      return 0
    fi
    if [[ "${phase}" == "Failed" ]]; then
      "${KUBECTL[@]}" delete pod zelkor-gvisor-preflight-smoke --wait=false >/dev/null 2>&1 || true
      return 1
    fi
    sleep 3
  done
  "${KUBECTL[@]}" delete pod zelkor-gvisor-preflight-smoke --wait=false >/dev/null 2>&1 || true
  return 1
}

MODE=""
CREATE_RC="true"

if ! "${KUBECTL[@]}" cluster-info >/dev/null 2>&1; then
  warn_or_fail "cluster unreachable; not installing gVisor on nodes"
  if [[ "$OPT_IN" == "true" ]]; then
    MODE="daemonset"
  else
    MODE="none"
    CREATE_RC="false"
  fi
else
  if "${KUBECTL[@]}" get nodes -l sandbox.gke.io/runtime=gvisor --no-headers 2>/dev/null | grep -q .; then
    MODE="preinstalled"
    CREATE_RC="false"
    log "GKE Sandbox node label detected; nodes will not be changed"
  elif "${KUBECTL[@]}" get runtimeclass gvisor >/dev/null 2>&1 && smoke_gvisor; then
    MODE="preinstalled"
    if gvisor_runtimeclass_owned_by_release; then
      CREATE_RC="true"
      log "RuntimeClass gvisor smoke pod succeeded; this release already renders it; nodes will not be changed"
    else
      CREATE_RC="false"
      log "RuntimeClass gvisor already exists and is not owned by this release; Helm will not adopt it; nodes will not be changed"
    fi
  fi

  runtimes="$("${KUBECTL[@]}" get nodes -o jsonpath='{range .items[*]}{.status.nodeInfo.containerRuntimeVersion}{"\n"}{end}' 2>/dev/null | sort -u || true)"
  if echo "${runtimes}" | grep -qi 'cri-o'; then
    warn_or_fail "CRI-O detected; gVisor containerd installer unsupported"
    MODE="none"
    CREATE_RC="false"
  elif ! echo "${runtimes}" | grep -qi 'containerd'; then
    warn_or_fail "no containerd nodes detected; gVisor installer may not work"
    if [[ -z "$MODE" ]]; then
      MODE="none"
      CREATE_RC="false"
    fi
  fi

  if [[ -z "$MODE" ]]; then
    if [[ "$OPT_IN" == "true" ]]; then
      MODE="daemonset"
      log "opt-in: will install runsc and restart the container runtime on selected nodes"
    else
      MODE="none"
      CREATE_RC="false"
      log "gVisor is not installed; pass --install-gvisor to change nodes, or --skip-gvisor"
    fi
  fi
fi

export GVISOR_PROVISIONING_MODE="${MODE}"
export GVISOR_CREATE_RUNTIME_CLASS="${CREATE_RC}"

case "${OUTPUT_FORMAT}" in
  shell)
    printf 'export GVISOR_PROVISIONING_MODE=%q\n' "${MODE}"
    printf 'export GVISOR_CREATE_RUNTIME_CLASS=%q\n' "${CREATE_RC}"
    ;;
  helm)
    printf '%s\n' "--set" "security.sandbox.provisioning.mode=${MODE}"
    printf '%s\n' "--set" "security.sandbox.createRuntimeClass=${CREATE_RC}"
    ;;
  *)
    echo "unknown output format: ${OUTPUT_FORMAT}" >&2
    exit 2
    ;;
esac
