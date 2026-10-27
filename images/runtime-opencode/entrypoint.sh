#!/bin/sh
# OpenCode behind zelkor-sidecar: loopback only, host shell/edit/web tools denied,
# model and MCP via the sidecar (OPENAI_BASE_URL / MCP_URL), no network fetches.
set -eu
: "${OPENAI_BASE_URL:?OPENAI_BASE_URL must point at the zelkor-sidecar loopback}"
: "${MCP_URL:?MCP_URL must point at the zelkor-sidecar loopback}"
model="${DEFAULT_LLM_MODEL:-${ZELKOR_OPENCODE_MODEL:-}}"
case "$model" in openai:*|ollama:*|anthropic:*) model="${model#*:}" ;; esac
: "${model:?set DEFAULT_LLM_MODEL (the gateway model id)}"
export ZELKOR_OPENCODE_MODEL="$model"
cd "${ZELKOR_AGENT_DIR:-/app}"
exec /opt/opencode/bin/opencode serve --hostname 127.0.0.1 --port "${ZELKOR_RUNTIME_PORT:-8080}"
