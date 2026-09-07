#!/usr/bin/env bash
# Finish a partial fast install: patch platform LLM, deploy FinServe, demo tour, verify traces.
# Run on the kind host (test server), not from a laptop kubectl context.
#
#   OLLAMA_API_KEY=... DEFAULT_LLM_MODEL=qwen3:8b ./scripts/finish-finserve-demo.sh
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

log() { echo "[finish-finserve] $*"; }

KCTX="${KUBECONTEXT:-kind-zelkor}"
CHART_PATH="${CHART_PATH:-charts/zelkor-platform}"
VALUES_FILE="${VALUES_FILE:-profiles/values-local-fast.yaml}"
FINSERVE_CHART="${FINSERVE_CHART_PATH:-examples/finserve/chart}"
FINSERVE_VALUES="${FINSERVE_VALUES_FILE:-${FINSERVE_CHART}/values-local.yaml}"
FINSERVE_OVERLAY="${FINSERVE_PLATFORM_OVERLAY:-${FINSERVE_CHART}/values-platform-overlay.yaml}"
MODEL="${DEFAULT_LLM_MODEL:-gpt-oss:20b}"
ROLLOUT_WAIT="${ROLLOUT_WAIT_TIMEOUT:-5m}"

if [[ -z "${OLLAMA_API_KEY:-}" ]]; then
  echo "[finish-finserve] ERROR: OLLAMA_API_KEY required" >&2
  exit 1
fi

if [[ "${BUILD_IMAGES:-false}" == true ]]; then
  log "building zelkor-aegra + zelkor-example-finserve (push to GHCR; kind load deprecated)..."
  IMAGES="zelkor-aegra zelkor-example-finserve" ./scripts/build-images.sh --push
fi

log "platform helm patch (Ollama Cloud, model=${MODEL})..."
kubectl --context "$KCTX" delete job zelkor-platform-langfuse-surfaces --ignore-not-found=true
helm upgrade zelkor-platform "$CHART_PATH" \
  --kube-context "$KCTX" \
  -f "$VALUES_FILE" \
  -f "$FINSERVE_OVERLAY" \
  --set "aiGateway.providers.ollamaCloud.apiKey=${OLLAMA_API_KEY}" \
  --set "guardrails.nemo.model=${MODEL}" \
  --set-string "langfuse.surfaces.llmConnection.models[0]=${MODEL}"

log "deploy FinServe..."
helm dependency update "$FINSERVE_CHART" >/dev/null
helm upgrade --install finserve "$FINSERVE_CHART" \
  --kube-context "$KCTX" \
  -f "$FINSERVE_VALUES" \
  --set-string "desk.platform.defaultLlmModel=${MODEL}" \
  --set-string "quant.platform.defaultLlmModel=${MODEL}" \
  --set-string "coder.platform.defaultLlmModel=${MODEL}"

log "wait FinServe seed jobs..."
kubectl --context "$KCTX" wait --for=condition=complete job -l app.kubernetes.io/instance=finserve --timeout=10m

log "wait FinServe rollouts..."
kubectl --context "$KCTX" rollout status deployment/finserve-desk --timeout="$ROLLOUT_WAIT"
kubectl --context "$KCTX" rollout status deployment/finserve-quant --timeout="$ROLLOUT_WAIT"
kubectl --context "$KCTX" rollout status deployment/finserve-coder --timeout="$ROLLOUT_WAIT"

export DEMO_TOUR=1
export KUBECONTEXT="$KCTX"
log "demo tour..."
./scripts/demo-tour.sh

log "verify finserve-advisor traces in Zelkor Platform project..."
PY="${ROOT}/.venv/bin/python3"
if [[ ! -x "$PY" ]]; then
  PY=python3
fi
"$PY" <<'PY'
import json
import sys
from datetime import datetime, timedelta, timezone

import httpx

base = "http://127.0.0.1:8088"
headers = {"Host": "langfuse.localhost"}
auth = ("pk-lf-zelkor-dev-00000000000000000000", "sk-lf-zelkor-dev-00000000000000000000")
since = (datetime.now(timezone.utc) - timedelta(minutes=20)).strftime("%Y-%m-%dT%H:%M:%SZ")
params = {
    "limit": 80,
    "fields": "core,basic,trace_context",
    "fromStartTime": since,
    "filter": json.dumps(
        [{"type": "string", "column": "traceName", "operator": "=", "value": "finserve-advisor"}]
    ),
}
resp = httpx.get(f"{base}/api/public/v2/observations", headers=headers, auth=auth, params=params, timeout=30)
print("langfuse HTTP", resp.status_code)
if resp.status_code != 200:
    print(resp.text[:500])
    sys.exit(1)
rows = resp.json().get("data") or []
trace_ids = sorted({r.get("traceId") for r in rows if r.get("traceId")})
print(f"observations={len(rows)} distinct_traces={len(trace_ids)}")
if not trace_ids:
    sys.exit("FAIL: no finserve-advisor traces in project Zelkor Platform")
print("OK trace_ids:", trace_ids[:5])
PY

log "done"
