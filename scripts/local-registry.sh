#!/usr/bin/env bash
# Start/stop/connect Zelkor pull-through proxy registries for kind local install.
#
# Usage (from repo root):
#   ./scripts/local-registry.sh start
#   ./scripts/local-registry.sh connect
#   ./scripts/local-registry.sh stop
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

LOCAL_REGISTRY_DOCKER_NAME="${LOCAL_REGISTRY_DOCKER_NAME:-zelkor-registry-docker}"
LOCAL_REGISTRY_GHCR_NAME="${LOCAL_REGISTRY_GHCR_NAME:-zelkor-registry-ghcr}"
LOCAL_REGISTRY_DOCKER_PORT="${LOCAL_REGISTRY_DOCKER_PORT:-5000}"
LOCAL_REGISTRY_GHCR_PORT="${LOCAL_REGISTRY_GHCR_PORT:-5001}"
LOCAL_REGISTRY_BIND="${LOCAL_REGISTRY_BIND:-127.0.0.1}"
REGISTRY_IMAGE="${REGISTRY_IMAGE:-registry:2}"
ZELKOR_REGISTRY_LABEL="${ZELKOR_REGISTRY_LABEL:-app=zelkor-local-registry}"
KIND_NETWORK="${KIND_NETWORK:-kind}"

log() { echo "[local-registry] $*"; }

port_in_use() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
    return $?
  fi
  (echo >/dev/tcp/"${LOCAL_REGISTRY_BIND#127.0.0.1}"/"$port") >/dev/null 2>&1
}

our_container_on_port() {
  local port="$1" name="$2"
  docker ps -a --filter "label=${ZELKOR_REGISTRY_LABEL}=true" --format '{{.Names}} {{.Ports}}' \
    | grep -q "^${name} .*${port}->" || return 1
}

start_one() {
  local name="$1" port="$2" config="$3"
  if docker ps --format '{{.Names}}' | grep -qx "$name"; then
    log "running: ${name} (${LOCAL_REGISTRY_BIND}:${port})"
    return 0
  fi
  if docker ps -a --format '{{.Names}}' | grep -qx "$name"; then
    log "starting existing container: ${name}"
    docker start "$name" >/dev/null
    return 0
  fi
  if port_in_use "$port" && ! our_container_on_port "$port" "$name"; then
    echo "[local-registry] ERROR: port ${LOCAL_REGISTRY_BIND}:${port} in use (set LOCAL_REGISTRY_*_PORT)" >&2
    exit 1
  fi
  log "creating ${name} on ${LOCAL_REGISTRY_BIND}:${port}"
  docker run -d \
    --restart=always \
    --label "${ZELKOR_REGISTRY_LABEL}=true" \
    --label "zelkor.dev/registry-role=${name}" \
    -p "${LOCAL_REGISTRY_BIND}:${port}:5000" \
    --name "$name" \
    -v "${config}:/etc/docker/registry/config.yml:ro" \
    "$REGISTRY_IMAGE" >/dev/null
}

stop_one() {
  local name="$1"
  if docker ps -a --format '{{.Names}}' | grep -qx "$name"; then
    docker rm -f "$name" >/dev/null 2>&1 || true
    log "removed ${name}"
  fi
}

cmd="${1:-start}"
case "$cmd" in
  start)
    start_one "$LOCAL_REGISTRY_DOCKER_NAME" "$LOCAL_REGISTRY_DOCKER_PORT" \
      "${ROOT}/images/install/registry-docker.config.yml"
    start_one "$LOCAL_REGISTRY_GHCR_NAME" "$LOCAL_REGISTRY_GHCR_PORT" \
      "${ROOT}/images/install/registry-ghcr.config.yml"
    ;;
  connect)
    if ! docker network inspect "$KIND_NETWORK" >/dev/null 2>&1; then
      echo "[local-registry] ERROR: docker network ${KIND_NETWORK} not found (create kind cluster first)" >&2
      exit 1
    fi
    for name in "$LOCAL_REGISTRY_DOCKER_NAME" "$LOCAL_REGISTRY_GHCR_NAME"; do
      if docker ps --format '{{.Names}}' | grep -qx "$name"; then
        if ! docker network inspect "$KIND_NETWORK" --format '{{range .Containers}}{{.Name}} {{end}}' \
          | grep -q "${name} "; then
          docker network connect "$KIND_NETWORK" "$name"
          log "connected ${name} to ${KIND_NETWORK}"
        fi
      fi
    done
    ;;
  stop)
    stop_one "$LOCAL_REGISTRY_DOCKER_NAME"
    stop_one "$LOCAL_REGISTRY_GHCR_NAME"
    ;;
  -h|--help)
    sed -n '2,12p' "$0"
    ;;
  *)
    echo "unknown command: $cmd" >&2
    exit 1
    ;;
esac
