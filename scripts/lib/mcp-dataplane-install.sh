# MCP Envoy dataplane: post-install waits and operator banners.
# Sourced by cluster-install.sh and install-engine.sh.

mcp_dataplane_kubectl() {
  kubectl "${MCP_DP_KUBECTL_ARGS[@]}" "$@"
}

mcp_dataplane_release() {
  echo "${MCP_DP_RELEASE:-zelkor-platform}"
}

mcp_dataplane_namespace() {
  echo "${MCP_DP_NAMESPACE:-zelkor}"
}

mcp_dataplane_route_name() {
  echo "$(mcp_dataplane_release)-mcp"
}

mcp_dataplane_wait_deployments() {
  local rel ns dep
  rel="$(mcp_dataplane_release)"
  ns="$(mcp_dataplane_namespace)"
  local targets=(
    "deployment/${rel}-mcp-postgres"
    "deployment/${rel}-mcp-qdrant"
    "deployment/${rel}-mcp-aigateway"
  )
  if mcp_dataplane_kubectl -n "$ns" get "deployment/${rel}-mcp-sandbox" >/dev/null 2>&1; then
    targets+=("deployment/${rel}-mcp-sandbox")
    local i
    for i in 0 1 2; do
      if mcp_dataplane_kubectl -n "$ns" get "deployment/${rel}-mcp-sandbox-worker-${i}" >/dev/null 2>&1; then
        targets+=("deployment/${rel}-mcp-sandbox-worker-${i}")
      fi
    done
  fi
  for dep in "${targets[@]}"; do
    if mcp_dataplane_kubectl -n "$ns" get "$dep" >/dev/null 2>&1; then
      echo "install: waiting for ${dep}"
      mcp_dataplane_kubectl -n "$ns" rollout status "$dep" --timeout=10m || return 1
    fi
  done
  return 0
}

mcp_dataplane_wait_mcproute() {
  local rel ns route
  rel="$(mcp_dataplane_release)"
  ns="$(mcp_dataplane_namespace)"
  route="$(mcp_dataplane_route_name)"
  if ! mcp_dataplane_kubectl -n "$ns" get mcproute "$route" >/dev/null 2>&1; then
    return 0
  fi
  echo "install: waiting for MCPRoute ${route} Accepted"
  local i status
  for i in $(seq 1 60); do
    status="$(mcp_dataplane_kubectl -n "$ns" get mcproute "$route" \
      -o jsonpath='{.status.conditions[?(@.type=="Accepted")].status}' 2>/dev/null || true)"
    if [[ "$status" == "True" ]]; then
      return 0
    fi
    sleep 5
  done
  echo "warning: MCPRoute ${route} not Accepted within timeout" >&2
  return 1
}

mcp_dataplane_wait_gateway() {
  local rel ns gw
  rel="$(mcp_dataplane_release)"
  ns="$(mcp_dataplane_namespace)"
  gw="${rel}-gateway"
  if ! mcp_dataplane_kubectl -n "$ns" get gateway "$gw" >/dev/null 2>&1; then
    return 0
  fi
  echo "install: waiting for Gateway ${gw}"
  local i gw_programmed listener_programmed reason
  for i in $(seq 1 60); do
    gw_programmed="$(mcp_dataplane_kubectl -n "$ns" get gateway "$gw" \
      -o jsonpath='{.status.conditions[?(@.type=="Programmed")].status}' 2>/dev/null || true)"
    listener_programmed="$(mcp_dataplane_kubectl -n "$ns" get gateway "$gw" \
      -o jsonpath='{.status.listeners[*].conditions[?(@.type=="Programmed")].status}' 2>/dev/null || true)"
    if [[ "$gw_programmed" == "True" || "$listener_programmed" == *"True"* ]]; then
      return 0
    fi
    sleep 5
  done
  reason="$(mcp_dataplane_kubectl -n "$ns" get gateway "$gw" \
    -o jsonpath='{.status.conditions[?(@.type=="Programmed")].reason}' 2>/dev/null || true)"
  echo "warning: Gateway ${gw} listeners not Programmed within timeout${reason:+ (${reason})}" >&2
  return 1
}

mcp_dataplane_wait_all() {
  mcp_dataplane_wait_gateway || true
  mcp_dataplane_wait_deployments || true
  mcp_dataplane_wait_mcproute || true
}

mcp_dataplane_print_token_banner() {
  local rel ctx_flag ns
  rel="$(mcp_dataplane_release)"
  ns="$(mcp_dataplane_namespace)"
  ctx_flag=""
  if [[ -n "${MCP_DP_KUBE_CONTEXT:-}" ]]; then
    ctx_flag=" --kube-context ${MCP_DP_KUBE_CONTEXT}"
  fi
  if [[ "${MCP_DP_LOCAL_SIGNING:-0}" != "1" ]]; then
    return 0
  fi
  cat <<EOF

======================================================================
  MCP tenant JWT (local signing)
======================================================================
  Mint RS256 tokens for agents and tests (reads ${rel}-tenant-jwt-signing):

    pip install -e ${ZELKOR_REPO_ROOT}/cli
    zelkor token mint --release ${rel} --tenant tenant-a --namespace ${ns}${ctx_flag}

  Export JWKS for an out-of-cluster agent:

    zelkor token jwks --release ${rel} --namespace ${ns}${ctx_flag} --out jwks.json

======================================================================
EOF
}
