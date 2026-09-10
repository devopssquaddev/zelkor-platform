#!/usr/bin/env bash
# Wait for Helm-managed gVisor installer and smoke-test RuntimeClass/gvisor.
# Legacy fallback: apply standalone DaemonSet when no Helm release owns the installer.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GVISOR_RELEASE="${GVISOR_RELEASE:-20260817}"
APPLY_RC=1
KUBECTL=(kubectl)
WAIT_TIMEOUT="${GVISOR_WAIT_TIMEOUT:-600}"
HELM_RELEASE="${HELM_RELEASE_NAME:-zelkor-platform}"

usage() {
  cat <<'EOF'
Usage: ./scripts/install-gvisor.sh [--kubeconfig PATH] [--kube-context NAME]
       [--release YYYYMMDD] [--no-runtimeclass] [--release-name NAME]

Waits for chart-managed zelkor-gvisor-installer (or applies legacy DaemonSet) and smoke-tests gvisor.
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
    --release)
      GVISOR_RELEASE="$2"
      shift 2
      ;;
    --release-name)
      HELM_RELEASE="$2"
      shift 2
      ;;
    --no-runtimeclass)
      APPLY_RC=0
      shift
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

log() { printf 'install-gvisor: %s\n' "$*"; }

smoke_gvisor() {
  "${KUBECTL[@]}" delete pod zelkor-gvisor-smoke --ignore-not-found --wait=false >/dev/null 2>&1 || true
  "${KUBECTL[@]}" apply -f - <<'EOF'
apiVersion: v1
kind: Pod
metadata:
  name: zelkor-gvisor-smoke
  namespace: default
spec:
  runtimeClassName: gvisor
  restartPolicy: Never
  tolerations:
    - operator: Exists
  containers:
    - name: smoke
      image: busybox:1.37.0
      command: ["dmesg"]
EOF
  local deadline=$((SECONDS + 120))
  while (( SECONDS < deadline )); do
    local phase="$("${KUBECTL[@]}" get pod zelkor-gvisor-smoke -o jsonpath='{.status.phase}' 2>/dev/null || true)"
    if [[ "${phase}" == "Succeeded" ]]; then
      "${KUBECTL[@]}" delete pod zelkor-gvisor-smoke --wait=false >/dev/null 2>&1 || true
      return 0
    fi
    if [[ "${phase}" == "Failed" ]]; then
      return 1
    fi
    sleep 3
  done
  return 1
}

find_installer_ds() {
  local name
  name="$("${KUBECTL[@]}" -n kube-system get ds -l app.kubernetes.io/component=gvisor-installer \
    -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"
  if [[ -n "${name}" ]]; then
    printf '%s' "${name}"
    return 0
  fi
  if "${KUBECTL[@]}" -n kube-system get ds zelkor-gvisor-installer >/dev/null 2>&1; then
    printf '%s' "zelkor-gvisor-installer"
    return 0
  fi
  if "${KUBECTL[@]}" -n kube-system get ds "${HELM_RELEASE}-gvisor-installer" >/dev/null 2>&1; then
    printf '%s' "${HELM_RELEASE}-gvisor-installer"
    return 0
  fi
  return 1
}

wait_installer() {
  local ds="$1"
  log "Waiting for ${ds} (${WAIT_TIMEOUT}s max)"
  local deadline=$((SECONDS + WAIT_TIMEOUT))
  while (( SECONDS < deadline )); do
    local ready desired
    ready="$("${KUBECTL[@]}" -n kube-system get ds "${ds}" -o jsonpath='{.status.numberReady}' 2>/dev/null || echo 0)"
    desired="$("${KUBECTL[@]}" -n kube-system get ds "${ds}" -o jsonpath='{.status.desiredNumberScheduled}' 2>/dev/null || echo 0)"
    if [[ "${ready:-0}" != "0" && "${ready}" == "${desired}" ]]; then
      log "installer ready on ${ready} node(s)"
      return 0
    fi
    sleep 5
  done
  return 1
}

apply_legacy_installer() {
  log "Applying legacy gVisor node installer (release ${GVISOR_RELEASE})"
  "${KUBECTL[@]}" create configmap zelkor-gvisor-install-script \
    --namespace kube-system \
    --from-file=install-on-node.sh="${DIR}/gvisor/install-on-node.sh" \
    --dry-run=client -o yaml | "${KUBECTL[@]}" apply -f -
  export GVISOR_RELEASE
  python3 - "${DIR}/gvisor/daemonset.yaml" <<'PY'
import os, pathlib, sys
text = pathlib.Path(sys.argv[1]).read_text()
text = text.replace('value: "20260817"', f'value: "{os.environ["GVISOR_RELEASE"]}"')
pathlib.Path("/tmp/zelkor-gvisor-ds.yaml").write_text(text)
PY
  "${KUBECTL[@]}" apply -f /tmp/zelkor-gvisor-ds.yaml
  rm -f /tmp/zelkor-gvisor-ds.yaml
  wait_installer "zelkor-gvisor-installer"
}

if [[ "${APPLY_RC}" -eq 1 ]] && ! "${KUBECTL[@]}" get runtimeclass gvisor >/dev/null 2>&1; then
  log "RuntimeClass gvisor not found (Helm chart should create it)"
fi

if ds="$(find_installer_ds)"; then
  wait_installer "${ds}" || {
    log "Helm-managed installer not ready"
    "${KUBECTL[@]}" -n kube-system get pods -l app.kubernetes.io/component=gvisor-installer -o wide || true
    exit 1
  }
else
  apply_legacy_installer
  if [[ "${APPLY_RC}" -eq 1 ]]; then
    log "Applying RuntimeClass gvisor (legacy)"
    "${KUBECTL[@]}" apply -f - <<'EOF'
apiVersion: node.k8s.io/v1
kind: RuntimeClass
metadata:
  name: gvisor
handler: runsc
EOF
  fi
fi

log "Smoke pod with RuntimeClass gvisor"
if smoke_gvisor; then
  log "gVisor smoke pod succeeded"
  exit 0
fi

log "gVisor smoke pod failed"
"${KUBECTL[@]}" describe pod zelkor-gvisor-smoke || true
exit 1
