#!/usr/bin/env bash
# Zelkor Platform — local bootstrap (dev entry point)
#
# Usage:
#   OPENAI_API_KEY=sk-... ./install.sh
#   OLLAMA_API_KEY=... ./install.sh
#   INSTALL_UX=plain ./install.sh          # raw engine logs (same as scripts/install-engine.sh)
#
# Rich UX (default on TTY): phase roadmap, heartbeats, install summary with start/end times.
# Engine logic lives in scripts/install-engine.sh (unchanged behavior at checkpoint).

set -euo pipefail

ZELKOR_REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ZELKOR_REPO_ROOT"

if [[ -z "${INSTALL_UX:-}" ]]; then
  if [[ -t 1 ]]; then
    INSTALL_UX=rich
  else
    INSTALL_UX=plain
  fi
fi

if [[ "$INSTALL_UX" == "plain" ]]; then
  exec "$ZELKOR_REPO_ROOT/scripts/install-engine.sh" "$@"
fi

export INSTALL_UX_RICH=true
export ZELKOR_UX_WRAPPED=true
export ZELKOR_REPO_ROOT

INSTALL_WALL_START_EPOCH=$(date +%s)
export START_TIME="$INSTALL_WALL_START_EPOCH"

UX_HEARTBEAT_PID=""
UX_CURRENT_PHASE=""
UX_LAST_STEP=""
UX_PHASE_TOTAL=5

ux_resolve_install_flags() {
  case "${INSTALL_PROFILE:-fast}" in
    fast)
      : "${INSTALL_EXAMPLES:=true}"
      : "${RUN_DEMO_TOUR:=true}"
      ;;
    full)
      : "${INSTALL_EXAMPLES:=true}"
      : "${RUN_DEMO_TOUR:=false}"
      ;;
  esac
  export INSTALL_EXAMPLES RUN_DEMO_TOUR
}

ux_phase_total() {
  if ux_demo_phase_enabled; then
    echo 6
  else
    echo 5
  fi
}

ux_demo_phase_enabled() {
  [[ "${INSTALL_PROFILE:-fast}" == "fast" && "${INSTALL_EXAMPLES:-true}" == "true" && "${RUN_DEMO_TOUR:-true}" == "true" ]]
}

# Typical cold-install duration (shown in roadmap and when each phase starts).
ux_phase_estimate() {
  local phase="$1"
  case "$phase" in
    1) echo "~2–3 min (untimed)" ;;
    2) echo "~2–3 min" ;;
    3) echo "~3–4 min" ;;
    4) echo "~5–8 min" ;;
    5) echo "~2–4 min" ;;
    6) echo "~5–7 min" ;;
    *) echo "" ;;
  esac
}

ux_format_ts() {
  local epoch="${1:-$(date +%s)}"
  if [[ "${INSTALL_UX_TIMESTAMPS:-}" == "iso" ]]; then
    if date -r 0 >/dev/null 2>&1; then
      date -r "$epoch" '+%Y-%m-%dT%H:%M:%S%z'
    else
      date -d "@$epoch" '+%Y-%m-%dT%H:%M:%S%z'
    fi
  else
    if date -r 0 >/dev/null 2>&1; then
      date -r "$epoch" '+%Y-%m-%d %H:%M:%S %Z'
    else
      date -d "@$epoch" '+%Y-%m-%d %H:%M:%S %Z'
    fi
  fi
}

INSTALL_WALL_START=$(ux_format_ts "$INSTALL_WALL_START_EPOCH")

ux_fmt_duration() {
  local total="${1:-0}"
  printf '%dm%02ds' $((total / 60)) $((total % 60))
}

ux_phase_for_step() {
  case "$1" in
    download_*)
      echo "1|Download components"
      ;;
    kind_create|registry_connect|gvisor_install|envoy_gateway|ai_gateway)
      echo "2|Cluster bootstrap"
      ;;
    platform_helm|rollout_datastores)
      echo "3|Datastores"
      ;;
    rollout_langfuse)
      echo "4|Langfuse"
      ;;
    rollout_aegra|rollout_mcp_nemo|job_langfuse_surfaces)
      echo "5|Agents & MCP"
      ;;
    finserve_helm|job_finserve_seed|rollout_finserve|demo_tour)
      if ux_demo_phase_enabled; then
        echo "6|FinServe demo"
      else
        echo "|"
      fi
      ;;
    *)
      echo "|"
      ;;
  esac
}

ux_phase_detail() {
  local phase="$1"
  local jobs="${PREFETCH_JOBS:-3}"
  case "$phase" in
    1)
      echo "  Warming ${jobs} container images in parallel via pull-through registries (untimed)."
      ;;
    2)
      echo "  kind cluster, registry connect, gVisor, Envoy Gateway, AI Gateway."
      ;;
    3)
      echo "  Platform Helm chart; Postgres, ClickHouse, Valkey, Qdrant rollouts."
      ;;
    4)
      echo "  Langfuse web + worker (DB migrations; often slowest on cold install)."
      ;;
    5)
      echo "  Aegra runtime, MCP gateway, NeMo guardrails, Langfuse surfaces seed."
      ;;
    6)
      echo "  FinServe example chart, seed, rollouts, then e2e smokes (sample Langfuse traces)."
      ;;
  esac
}

ux_heartbeat_stop() {
  if [[ -n "$UX_HEARTBEAT_PID" ]]; then
    kill "$UX_HEARTBEAT_PID" 2>/dev/null || true
    wait "$UX_HEARTBEAT_PID" 2>/dev/null || true
    UX_HEARTBEAT_PID=""
  fi
}

ux_heartbeat_start() {
  local msg="$1"
  ux_heartbeat_stop
  (
    while true; do
      sleep 30
      local el=$(( $(date +%s) - INSTALL_WALL_START_EPOCH ))
      printf '\n  … still working (%dm%02ds) — %s\n' $((el / 60)) $((el % 60)) "$msg"
    done
  ) &
  UX_HEARTBEAT_PID=$!
}

ux_step_begin() {
  local step="$1"
  UX_LAST_STEP="$step"
  local info
  info="$(ux_phase_for_step "$step")"
  local phase="${info%%|*}"
  local label="${info#*|}"
  if [[ -n "$phase" && "$phase" != "$info" ]]; then
    if [[ "$phase" != "$UX_CURRENT_PHASE" ]]; then
      UX_CURRENT_PHASE="$phase"
      local eta
      eta="$(ux_phase_estimate "$phase")"
      printf '\n[Phase %s/%s] %s  (%s)\n' "$phase" "$UX_PHASE_TOTAL" "$label" "$eta"
      ux_phase_detail "$phase"
    fi
  fi
  case "$step" in
    rollout_langfuse)
      ux_heartbeat_start "Langfuse rollout (migrations + pods; often 5–8 min cold)"
      ;;
    rollout_datastores)
      ux_heartbeat_start "Datastore rollouts (Postgres, ClickHouse, Valkey, Qdrant)"
      ;;
    download_warm_cache)
      ux_heartbeat_start "Warming image cache (${PREFETCH_JOBS:-3} parallel pulls via local registries)"
      ;;
  esac
}

ux_step_end() {
  ux_heartbeat_stop
}

ux_wait_group_begin() {
  local label="$1"
  case "$label" in
    *Langfuse*|*langfuse*)
      ux_heartbeat_start "Waiting for Langfuse (${label})"
      ;;
    *datastore*|*Datastore*)
      ux_heartbeat_start "Waiting for datastores (${label})"
      ;;
  esac
}

ux_wait_group_end() {
  ux_heartbeat_stop
}

ux_wait_one_begin() {
  local target="$1"
  case "$target" in
    *langfuse*)
      ux_heartbeat_start "Waiting for ${target}"
      ;;
  esac
}

ux_wait_one_end() {
  ux_heartbeat_stop
}

ux_print_roadmap() {
  ux_resolve_install_flags
  UX_PHASE_TOTAL="$(ux_phase_total)"
  local jobs="${PREFETCH_JOBS:-3}"

  cat <<EOF

======================================================================
  Zelkor install
======================================================================
  Started: ${INSTALL_WALL_START}

  Phase 1/${UX_PHASE_TOTAL}  Download components           ($(ux_phase_estimate 1); ${jobs} parallel pulls)
  Phase 2/${UX_PHASE_TOTAL}  Cluster bootstrap             ($(ux_phase_estimate 2))
  Phase 3/${UX_PHASE_TOTAL}  Datastores                    ($(ux_phase_estimate 3))
  Phase 4/${UX_PHASE_TOTAL}  Langfuse                      ($(ux_phase_estimate 4))
  Phase 5/${UX_PHASE_TOTAL}  Agents & MCP                  ($(ux_phase_estimate 5))
EOF
  if ux_demo_phase_enabled; then
    cat <<EOF
  Phase 6/${UX_PHASE_TOTAL}  FinServe demo                 ($(ux_phase_estimate 6); deploy + sample traces)
EOF
  fi
  cat <<EOF

  Re-runs on an existing kind cluster are usually much faster.

======================================================================

EOF
}

ux_print_summary() {
  local end_epoch="${END_TIME:-$(date +%s)}"
  local end_ts
  end_ts="$(ux_format_ts "$end_epoch")"
  local wall="${WALL_DURATION:-$((end_epoch - INSTALL_WALL_START_EPOCH))}"
  local install="${INSTALL_DURATION:-$((end_epoch - INSTALL_WALL_START_EPOCH))}"
  local download="${DOWNLOAD_DURATION:-0}"

  cat <<EOF

======================================================================
  Install summary
======================================================================
  Started:   ${INSTALL_WALL_START}
  Finished:  ${end_ts}
  Wall:      $(ux_fmt_duration "$wall")
EOF

  if [[ "$download" -gt 0 ]]; then
    cat <<EOF
  Download:  $(ux_fmt_duration "$download") (outside install timer)
  Install:   $(ux_fmt_duration "$install") (timed steps)
EOF
  else
    cat <<EOF
  Install:   $(ux_fmt_duration "$install")
EOF
  fi

  if [[ -s "${INSTALL_TIMINGS_FILE:-}" ]]; then
    echo ""
    echo "  Slowest steps:"
    sort -t$'\t' -k2 -nr "${INSTALL_TIMINGS_FILE}" | head -3 | while IFS=$'\t' read -r step secs; do
      printf '    %s: %ss\n' "$step" "$secs"
    done
  fi

  if [[ "${DEMO_TOUR_FAILED:-false}" == "true" ]]; then
    echo ""
    echo "  Demo tour: some checks did not pass (LLM non-determinism; install OK)"
  elif [[ "${RUN_DEMO_TOUR:-true}" == "true" && "${INSTALL_PROFILE:-fast}" == "fast" && "${INSTALL_EXAMPLES:-true}" == "true" ]]; then
    echo ""
    echo "  Demo tour: completed"
  fi

  cat <<EOF
======================================================================

EOF
}

ux_print_roadmap
# shellcheck source=scripts/install-engine.sh
source "$ZELKOR_REPO_ROOT/scripts/install-engine.sh"
ux_print_summary
install_print_access_footer
