#!/usr/bin/env bash
# FinServe showcase e2e smokes for fast-profile install (sample traces + feature proof).
#
# Usage (from repo root):
#   ./scripts/demo-tour.sh
#   RUN_DEMO_TOUR=false ./install.sh   # skip via install.sh
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

log() { echo "[demo-tour] $*"; }

export GATEWAY_BASE_URL="${GATEWAY_BASE_URL:-http://127.0.0.1:8088}"
export KUBECONTEXT="${KUBECONTEXT:-kind-zelkor}"
export AEGRA_HOST_HEADER="${AEGRA_HOST_HEADER:-aegra.localhost}"
export LANGFUSE_HOST_HEADER="${LANGFUSE_HOST_HEADER:-langfuse.localhost}"
export DEMO_TOUR=1

wait_for_gateway() {
  local url="${GATEWAY_BASE_URL}/health"
  local i
  log "waiting for gateway at ${GATEWAY_BASE_URL} (Host: ${AEGRA_HOST_HEADER})..."
  for i in $(seq 1 60); do
    if curl -fsS -o /dev/null -H "Host: ${AEGRA_HOST_HEADER}" "${url}" 2>/dev/null; then
      log "gateway ready"
      return 0
    fi
    sleep 2
  done
  echo "[demo-tour] ERROR: gateway not reachable at ${url}" >&2
  return 1
}

if [[ ! -d .venv ]]; then
  log "creating Python venv for demo smokes..."
  python3 -m venv .venv
  .venv/bin/pip install --upgrade pip >/dev/null
  .venv/bin/pip install -r requirements-dev.txt >/dev/null
fi

PYTEST=(.venv/bin/pytest)

# Curated FinServe smokes: routing, Langfuse waterfall, tenant isolation, sandbox, NeMo guardrails.
# Prompts are tool-minimal (0–1 MCP call per run) — see examples/finserve/tests/finserve_e2e.py.
DEMO_TESTS=(
  "examples/finserve/tests/test_base01_install.py::test_base01_finserve_runs_via_front_door[finserve-advisor]"
  "examples/finserve/tests/test_base01_install.py::test_base01_finserve_agent_generates_traces"
  "examples/finserve/tests/test_base02_tenant_isolation.py::test_base02_tenant_isolation_authorized_access"
  "examples/finserve/tests/test_base02_tenant_isolation.py::test_base02_tenant_isolation_idor_smoke"
  "examples/finserve/tests/test_base03_gvisor_sandbox.py::test_base03_agent_code_execution_smoke"
  "examples/finserve/tests/test_base03_gvisor_sandbox.py::test_base03_sandbox_trace_contains_tool"
  "examples/finserve/tests/test_base05_nemo_guardrails.py::test_base05_agent_on_topic_smoke"
  "examples/finserve/tests/test_base05_nemo_guardrails.py::test_base05_agent_off_topic_guardrail_smoke"
)

wait_for_gateway

log "running ${#DEMO_TESTS[@]} FinServe showcase tests..."
log "Langfuse: project Zelkor Platform (pk-lf-zelkor-dev-*); trace names finserve-advisor, finserve-quant (sandbox__execute_python)"
# Plain text by default: a non-deterministic LLM smoke should not print red in an install.
"${PYTEST[@]}" "${DEMO_TESTS[@]}" -v --tb=short --color="${DEMO_TOUR_PYTEST_COLOR:-no}"
log "done — open http://langfuse.localhost:8088 → project Zelkor Platform → Traces (filter: finserve-advisor)"
