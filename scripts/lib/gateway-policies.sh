# Gateway policies chart (K11 control 1): listener derivation and preflight.
# Sourced by bootstrap-gateway.sh and cluster-install.sh.

gateway_policies_resolve_tls() {
  GATEWAY_POLICIES_TLS_ENABLED="${GATEWAY_POLICIES_TLS_ENABLED:-0}"
  GATEWAY_POLICIES_TLS_PORT="${GATEWAY_POLICIES_TLS_PORT:-443}"
  local arg
  for arg in "${GATEWAY_POLICIES_HELM_SET_SCAN[@]:-}"; do
    case "$arg" in
      gateway.tls.enabled=true) GATEWAY_POLICIES_TLS_ENABLED=1 ;;
      gateway.tls.enabled=false) GATEWAY_POLICIES_TLS_ENABLED=0 ;;
      gateway.tls.port=*) GATEWAY_POLICIES_TLS_PORT="${arg#gateway.tls.port=}" ;;
    esac
  done
}

gateway_policies_listeners_json() {
  gateway_policies_resolve_tls
  python3 -c 'import json, os
tls = os.environ.get("GATEWAY_POLICIES_TLS_ENABLED", "0") == "1"
port = int(os.environ.get("GATEWAY_POLICIES_TLS_PORT", "443"))
listeners = [{"port": 80}]
if tls:
    listeners.append({"port": port})
print(json.dumps(listeners))'
}

gateway_policies_gateway_name() {
  local release="${1:-zelkor-platform}"
  local parent="${2:-}"
  if [[ -n "$parent" ]]; then
    echo "$parent"
  else
    echo "${release}-gateway"
  fi
}

gateway_policies_gateway_namespace() {
  local platform_ns="${1:-zelkor}"
  local parent_ns="${2:-}"
  if [[ -n "$parent_ns" ]]; then
    echo "$parent_ns"
  else
    echo "$platform_ns"
  fi
}

gateway_policies_platform_listener_ports() {
  local chart="$1"
  local namespace="$2"
  local release="$3"
  shift 3
  local rendered
  rendered=$(helm template "$release" "$chart" --namespace "$namespace" "$@" 2>/dev/null) || return 1
  printf '%s' "$rendered" | python3 -c 'import sys, yaml
ports=set()
for doc in yaml.safe_load_all(sys.stdin.read()):
    if not doc or doc.get("kind") != "Gateway":
        continue
    for lis in (doc.get("spec") or {}).get("listeners") or []:
        p = lis.get("port")
        if p is not None:
            ports.add(int(p))
if not ports:
    raise SystemExit(1)
print(" ".join(str(p) for p in sorted(ports)))'
}

gateway_policies_release_listener_ports() {
  local helm_args=("$@")
  local json
  json=$(helm "${helm_args[@]}" get values zelkor-gateway-policies -n envoy-gateway-system -o json 2>/dev/null) || return 1
  printf '%s' "$json" | python3 -c 'import json, sys
data = json.load(sys.stdin)
listeners = data.get("listeners") or []
ports = []
for item in listeners:
    if isinstance(item, dict):
        ports.append(int(item["port"]))
    else:
        ports.append(int(item))
print(" ".join(str(p) for p in sorted(ports)))'
}

gateway_policies_preflight_match() {
  local expected="$1"
  local actual="$2"
  [[ -n "$expected" && -n "$actual" ]] || return 0
  if [[ "$expected" != "$actual" ]]; then
    echo "gateway listener ports (${expected}) not covered by zelkor-gateway-policies listeners (${actual})" >&2
    return 1
  fi
  return 0
}
