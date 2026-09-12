# Ownership record for Zelkor-installed cluster bootstrap (Envoy / operators).
# Sourced by bootstrap-gateway.sh, bootstrap-operators.sh, and uninstall.sh.
# ConfigMap is the source of truth. Skip-if-exists paths must not record.

ZELKOR_OWNERSHIP_NS="${ZELKOR_OWNERSHIP_NS:-kube-system}"
ZELKOR_OWNERSHIP_CM="${ZELKOR_OWNERSHIP_CM:-zelkor-bootstrap-ownership}"
ZELKOR_BOOTSTRAP_ANNOTATION="zelkor.io/bootstrap=true"

zelkor_ownership_keys_from_env() {
  local raw="${ZELKOR_BOOTSTRAP_OWNERSHIP:-}"
  raw="${raw//,/ }"
  # shellcheck disable=SC2086
  printf '%s\n' $raw
}

zelkor_ownership_owns() {
  local key="$1"
  if [[ -n "${ZELKOR_BOOTSTRAP_OWNERSHIP:-}" || "${ZELKOR_BOOTSTRAP_DRY_RUN:-0}" == "1" ]]; then
    local item
    while IFS= read -r item; do
      [[ "$item" == "$key" ]] && return 0
    done < <(zelkor_ownership_keys_from_env)
    return 1
  fi
  local val
  val=$(kubectl "${KUBECTL_ARGS[@]}" get configmap "$ZELKOR_OWNERSHIP_CM" \
    -n "$ZELKOR_OWNERSHIP_NS" \
    -o "jsonpath={.data.${key}}" 2>/dev/null || true)
  [[ "$val" == "installed" ]]
}

zelkor_ownership_ns_owned() {
  local ns="$1"
  if [[ -n "${ZELKOR_BOOTSTRAP_OWNERSHIP:-}" || "${ZELKOR_BOOTSTRAP_DRY_RUN:-0}" == "1" ]]; then
    return 1
  fi
  local val
  val=$(kubectl "${KUBECTL_ARGS[@]}" get namespace "$ns" \
    -o "jsonpath={.metadata.annotations.zelkor\.io/bootstrap}" 2>/dev/null || true)
  [[ "$val" == "true" ]]
}

zelkor_ownership_record() {
  local key="$1"
  if [[ "${ZELKOR_BOOTSTRAP_DRY_RUN:-0}" == "1" ]]; then
    echo "OWNERSHIP_RECORD ${key}"
    return 0
  fi
  kubectl "${KUBECTL_ARGS[@]}" create namespace "$ZELKOR_OWNERSHIP_NS" \
    --dry-run=client -o yaml | kubectl "${KUBECTL_ARGS[@]}" apply -f - >/dev/null
  if ! kubectl "${KUBECTL_ARGS[@]}" get configmap "$ZELKOR_OWNERSHIP_CM" \
    -n "$ZELKOR_OWNERSHIP_NS" >/dev/null 2>&1; then
    kubectl "${KUBECTL_ARGS[@]}" create configmap "$ZELKOR_OWNERSHIP_CM" \
      -n "$ZELKOR_OWNERSHIP_NS" \
      --from-literal="${key}=installed" >/dev/null
  else
    kubectl "${KUBECTL_ARGS[@]}" patch configmap "$ZELKOR_OWNERSHIP_CM" \
      -n "$ZELKOR_OWNERSHIP_NS" \
      --type merge \
      -p "{\"data\":{\"${key}\":\"installed\"}}" >/dev/null
  fi
  echo "ownership: recorded ${key}"
}

zelkor_ownership_annotate_ns() {
  local ns="$1"
  if [[ "${ZELKOR_BOOTSTRAP_DRY_RUN:-0}" == "1" ]]; then
    echo "OWNERSHIP_ANNOTATE_NS ${ns}"
    return 0
  fi
  kubectl "${KUBECTL_ARGS[@]}" annotate namespace "$ns" \
    "$ZELKOR_BOOTSTRAP_ANNOTATION" --overwrite >/dev/null
}

# Decide whether to write envoy-gateway-config.
# args: eg_ready(0|1) owned(0|1) patch_flag(0|1) skip_ai(0|1)
# prints: apply | skip | fail
zelkor_eg_patch_action() {
  local eg_ready="$1"
  local owned="$2"
  local patch_flag="$3"
  local skip_ai="$4"
  if [[ "$eg_ready" -eq 0 ]]; then
    echo apply
    return 0
  fi
  if [[ "$owned" -eq 1 ]]; then
    echo apply
    return 0
  fi
  if [[ "$patch_flag" -eq 1 ]]; then
    echo apply
    return 0
  fi
  if [[ "$skip_ai" -eq 0 ]]; then
    echo fail
    return 0
  fi
  echo skip
}
