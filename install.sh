#!/usr/bin/env bash
# Zelkor Platform — local bootstrap (dev entry point)
#
# Usage:
#   OPENAI_API_KEY=sk-... ./install.sh
#   OLLAMA_API_KEY=... ./install.sh
#   IMAGE_TAG=dev ./install.sh            # unreleased local builds only; default is Chart.yaml appVersion
#   INSTALL_UX=plain ./install.sh          # raw engine logs (same as scripts/install-engine.sh)
#   INSTALL_LOG_FILE=/tmp/zelkor-install.log ./install.sh   # default; set off to disable
#   (Same log env on scripts/install-production.sh and scripts/install-quickstart.sh.)
#
# Rich UX (default on a TTY, unless NO_COLOR is set): live phase checklist on the
# terminal. Helm/kubectl and [install +MM:SS] lines go only to INSTALL_LOG_FILE.
# Engine logic lives in scripts/install-engine.sh.

set -euo pipefail

ZELKOR_REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ZELKOR_REPO_ROOT"

# shellcheck source=scripts/lib/install-log.sh
source "${ZELKOR_REPO_ROOT}/scripts/lib/install-log.sh"

local_install_prepare_engine() {
  # shellcheck source=scripts/lib/local-install-display.sh
  source "${ZELKOR_REPO_ROOT}/scripts/lib/local-install-display.sh"
  local_install_export_display_env
}

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

# Typical cold-install duration (shown while a phase is pending or running).
ux_phase_estimate() {
  local phase="$1"
  case "$phase" in
    1) echo "~2-3 min (untimed)" ;;
    2) echo "~2-3 min" ;;
    3) echo "~3-4 min" ;;
    4) echo "~5-8 min" ;;
    5) echo "~2-4 min" ;;
    6) echo "~5-7 min" ;;
    *) echo "" ;;
  esac
}

ux_phase_label() {
  case "$1" in
    1) echo "Download components" ;;
    2) echo "Cluster bootstrap" ;;
    3) echo "Datastores" ;;
    4) echo "Langfuse" ;;
    5) echo "Agents & MCP" ;;
    6) echo "FinServe demo" ;;
    *) echo "Phase $1" ;;
  esac
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
    rollout_aegra|rollout_mcp_nemo|job_langfuse_surfaces|job_langfuse_bootstrap)
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

ux_step_hint() {
  local jobs="${PREFETCH_JOBS:-3}"
  case "$1" in
    download_warm_cache|download_registry_start)
      echo "Fetching images (${jobs} at a time)"
      ;;
    rollout_langfuse)
      echo "Langfuse migrations and pods"
      ;;
    rollout_datastores)
      echo "Postgres, ClickHouse, Valkey, Qdrant"
      ;;
    *)
      echo ""
      ;;
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

ux_fmt_duration() {
  local total="${1:-0}"
  printf '%dm%02ds' $((total / 60)) $((total % 60))
}

ux_init_colors() {
  if [[ -z "${NO_COLOR:-}" && "${INSTALL_STDOUT_IS_TTY:-}" == "1" ]]; then
    C_GREEN=$'\033[32m'
    C_YELLOW=$'\033[33m'
    C_RED=$'\033[31m'
    C_CYAN=$'\033[36m'
    C_DIM=$'\033[2m'
    C_BOLD=$'\033[1m'
    C_RESET=$'\033[0m'
  else
    C_GREEN=''
    C_YELLOW=''
    C_RED=''
    C_CYAN=''
    C_DIM=''
    C_BOLD=''
    C_RESET=''
  fi
  export C_GREEN C_YELLOW C_RED C_CYAN C_DIM C_BOLD C_RESET
}

ux_init_glyphs() {
  local charmap=""
  charmap="$(locale charmap 2>/dev/null || true)"
  if [[ -z "$charmap" && "${LC_ALL:-}${LC_CTYPE:-}${LANG:-}" == *UTF-8* ]]; then
    charmap="UTF-8"
  fi
  if [[ "$charmap" == "UTF-8" ]]; then
    UX_UTF8=1
    UX_TL='╭' UX_TR='╮' UX_BL='╰' UX_BR='╯'
    UX_H='─' UX_V='│'
    UX_MARK_DONE='✓' UX_MARK_RUN='◉' UX_MARK_PEND='○' UX_MARK_SKIP='–' UX_MARK_FAIL='✗'
    UX_SEP='·'
    UX_SPIN_FRAMES=('⠋' '⠙' '⠹' '⠸' '⠼' '⠴' '⠦' '⠧' '⠇' '⠏')
  else
    UX_UTF8=0
    UX_TL='+' UX_TR='+' UX_BL='+' UX_BR='+'
    UX_H='-' UX_V='|'
    UX_MARK_DONE='[ok]' UX_MARK_RUN='[>>]' UX_MARK_PEND='[..]' UX_MARK_SKIP='[--]' UX_MARK_FAIL='[!!]'
    UX_SEP='|'
    UX_SPIN_FRAMES=('|' '/' '-' '\')
  fi
  UX_BOX_W=68
}

ux_hr() {
  local ch="$1" n="$2" out="" i
  for ((i = 0; i < n; i++)); do
    out+="$ch"
  done
  printf '%s' "$out"
}

ux_clip() {
  local text="$1" max="$2"
  if ((${#text} <= max)); then
    printf '%s' "$text"
    return 0
  fi
  printf '%s...' "${text:0:$((max - 3))}"
}

ux_box_top() {
  local title="$1"
  local rest=$((UX_BOX_W - 5 - ${#title}))
  if ((rest < 1)); then
    rest=1
  fi
  printf '%s%s %s %s%s' "$UX_TL" "$UX_H" "$title" "$(ux_hr "$UX_H" "$rest")" "$UX_TR"
}

ux_box_row() {
  local text="$1"
  local max=$((UX_BOX_W - 4))
  if ((${#text} > max)); then
    text="${text:0:$((max - 3))}..."
  fi
  local pad=$((max - ${#text}))
  printf '%s %s%*s %s' "$UX_V" "$text" "$pad" "" "$UX_V"
}

ux_box_bottom() {
  printf '%s%s%s' "$UX_BL" "$(ux_hr "$UX_H" "$((UX_BOX_W - 2))")" "$UX_BR"
}

ux_phase_set() {
  local n="$1" v="$2"
  eval "UX_PHASE_STATE_${n}=\"\$v\""
}

ux_phase_get() {
  local n="$1" v
  eval "v=\${UX_PHASE_STATE_${n}:-pending}"
  printf '%s' "$v"
}

ux_phase_begin() {
  local n="$1" now
  now=$(date +%s)
  eval "UX_PHASE_T0_${n}=\${now}"
  ux_phase_set "$n" running
}

ux_phase_finish() {
  local n="$1" now t0
  now=$(date +%s)
  eval "t0=\${UX_PHASE_T0_${n}:-\$now}"
  eval "UX_PHASE_SECS_${n}=\$((now - t0))"
  ux_phase_set "$n" done
}

ux_phase_timing() {
  local n="$1" st secs
  st="$(ux_phase_get "$n")"
  case "$st" in
    done)
      eval "secs=\${UX_PHASE_SECS_${n}:-0}"
      ux_fmt_duration "$secs"
      ;;
    skipped)
      echo "skipped"
      ;;
    *)
      ux_phase_estimate "$n"
      ;;
  esac
}

ux_init_files() {
  local dir="${TMPDIR:-/tmp}"
  UX_LOCK="${dir}/zelkor-ux-$$.lock"
  UX_MSG_FILE="${dir}/zelkor-ux-$$.msg"
  UX_TIMER_FILE="${dir}/zelkor-ux-$$.timer"
  rm -rf "$UX_LOCK"
  echo "${INSTALL_START_TIME:-${START_TIME:-$(date +%s)}}" >"$UX_TIMER_FILE"
  printf 'install\tstarting\n' >"$UX_MSG_FILE"
}

ux_set_status() {
  local step="$1" msg="$2"
  printf '%s\t%s\n' "$step" "$msg" >"${UX_MSG_FILE:?}"
  echo "${INSTALL_START_TIME:-${START_TIME:-0}}" >"${UX_TIMER_FILE:?}"
}

ux_printf() {
  if [[ "${UX_FORCE_FD:-}" == "3" ]]; then
    printf "$@" >&3
    return 0
  fi
  if [[ -e /dev/tty && -w /dev/tty ]]; then
    printf "$@" >/dev/tty
    return 0
  fi
  printf "$@" >&3
}

ux_puts() {
  ux_printf '%s\n' "$1"
}

ux_lock_acquire() {
  local i=0
  while ! mkdir "$UX_LOCK" 2>/dev/null; do
    i=$((i + 1))
    if ((i > 50)); then
      rm -rf "$UX_LOCK"
      i=0
    fi
    sleep 0.02
  done
}

ux_lock_release() {
  rmdir "$UX_LOCK" 2>/dev/null || rm -rf "$UX_LOCK"
}

ux_phase_row() {
  local n="$1" st mark timing label
  st="$(ux_phase_get "$n")"
  label="$(ux_phase_label "$n")"
  timing="$(ux_phase_timing "$n")"
  case "$st" in
    done) mark="${C_GREEN}${UX_MARK_DONE}${C_RESET}" ;;
    running) mark="${C_CYAN}${UX_MARK_RUN}${C_RESET}" ;;
    failed) mark="${C_RED}${UX_MARK_FAIL}${C_RESET}" ;;
    skipped) mark="${C_DIM}${UX_MARK_SKIP}${C_RESET}" ;;
    *) mark="${C_DIM}${UX_MARK_PEND}${C_RESET}" ;;
  esac
  if [[ "$st" == "pending" || "$st" == "skipped" ]]; then
    printf '  %s  %-22s  %s%s%s' "$mark" "$label" "$C_DIM" "$timing" "$C_RESET"
  else
    printf '  %s  %-22s  %s' "$mark" "$label" "$timing"
  fi
}

ux_status_line() {
  if [[ "${UX_PANEL_FROZEN:-}" == "1" ]]; then
    if [[ "${UX_STATUS_STATIC:-}" == "failed" ]]; then
      printf '  %s  failed' "${C_RED}${UX_MARK_FAIL}${C_RESET}"
    else
      printf '  %s  complete' "${C_GREEN}${UX_MARK_DONE}${C_RESET}"
    fi
    return 0
  fi
  local raw step msg
  raw="$(cat "${UX_MSG_FILE:-/dev/null}" 2>/dev/null || true)"
  step="${raw%%$'\t'*}"
  msg="${raw#*$'\t'}"
  [[ "$msg" == "$raw" ]] && msg=""
  printf '  %s  %-18s %s' "${C_CYAN}${UX_MARK_RUN}${C_RESET}" "$step" "$msg"
}

ux_render_panel() {
  local profile cluster log_disp note row1 row2 rows=() p
  profile="${INSTALL_PROFILE:-fast}"
  cluster="${CLUSTER_NAME:-zelkor}"
  log_disp="$(ux_clip "${INSTALL_LOG_FILE:-/tmp/zelkor-install.log}" 48)"
  if [[ "$profile" == "full" ]]; then
    row1="full upgrade ${UX_SEP} cluster ${cluster}"
    note="Needs a completed fast install. Skips download."
  else
    row1="fast ${UX_SEP} cluster ${cluster}"
    note="Re-runs on an existing cluster are faster."
  fi
  row2="log ${log_disp}"
  rows+=("$(ux_box_top "Zelkor local install")")
  rows+=("$(ux_box_row "$row1")")
  rows+=("$(ux_box_row "$row2")")
  rows+=("$(ux_box_row "$note")")
  rows+=("$(ux_box_bottom)")
  rows+=("")
  for ((p = 1; p <= UX_PHASE_TOTAL; p++)); do
    rows+=("$(ux_phase_row "$p")")
  done
  rows+=("")
  rows+=("$(ux_status_line)")
  local IFS=$'\n'
  printf '%s' "${rows[*]}"
}

ux_redraw() {
  local panel lines
  panel="$(ux_render_panel)"
  lines=$(printf '%s\n' "$panel" | wc -l | tr -d ' ')
  ux_lock_acquire
  if [[ "${UX_PANEL_LINES:-0}" -gt 0 ]]; then
    ux_printf '\033[%dA\033[J' "$UX_PANEL_LINES"
  fi
  ux_printf '%s\n' "$panel"
  ux_lock_release
  UX_PANEL_LINES=$lines
}

ux_spinner_start() {
  [[ -n "${UX_HEARTBEAT_PID:-}" ]] && return 0
  (
    trap - ERR EXIT
    set +eu
    local i=0 n=${#UX_SPIN_FRAMES[@]} last_log=$SECONDS
    local base now el frame raw step msg
    while true; do
      base=$(cat "$UX_TIMER_FILE" 2>/dev/null || echo 0)
      now=$(date +%s)
      el=$((now - base))
      if ((el < 0)); then
        el=0
      fi
      raw=$(cat "$UX_MSG_FILE" 2>/dev/null || true)
      step="${raw%%$'\t'*}"
      msg="${raw#*$'\t'}"
      [[ "$msg" == "$raw" ]] && msg=""
      msg="${msg:0:42}"
      frame="${UX_SPIN_FRAMES[$i]}"
      ux_lock_acquire
      ux_printf '\033[1A\r\033[K  %s  %-18s +%02d:%02d  %s\n' \
        "$frame" "$step" $((el / 60)) $((el % 60)) "$msg"
      ux_lock_release
      i=$(((i + 1) % n))
      if ((SECONDS - last_log >= 30)); then
        last_log=$SECONDS
        if [[ -n "${INSTALL_LOG_FILE:-}" && -f "$INSTALL_LOG_FILE" ]]; then
          printf '[install +%02d:%02d] still working — %s %s\n' \
            $((el / 60)) $((el % 60)) "$step" "$msg" >>"$INSTALL_LOG_FILE"
        fi
      fi
      sleep 0.2
    done
  ) &
  UX_HEARTBEAT_PID=$!
}

ux_heartbeat_stop() {
  local pid="${UX_HEARTBEAT_PID:-}"
  [[ -n "$pid" ]] || return 0
  kill "$pid" 2>/dev/null || true
  wait "$pid" 2>/dev/null || true
  UX_HEARTBEAT_PID=""
  [[ -n "${UX_LOCK:-}" ]] && rm -rf "$UX_LOCK"
}

ux_cleanup() {
  ux_heartbeat_stop || true
  [[ -n "${UX_LOCK:-}" ]] && rm -rf "$UX_LOCK"
  [[ -n "${UX_MSG_FILE:-}" ]] && rm -f "$UX_MSG_FILE"
  [[ -n "${UX_TIMER_FILE:-}" ]] && rm -f "$UX_TIMER_FILE"
}

ux_tail_log() {
  [[ -n "${INSTALL_LOG_FILE:-}" && -f "$INSTALL_LOG_FILE" ]] || return 0
  if [[ "${UX_FORCE_FD:-}" == "3" ]]; then
    tail -n 40 "$INSTALL_LOG_FILE" >&3 || true
  elif [[ -w /dev/tty ]]; then
    tail -n 40 "$INSTALL_LOG_FILE" >/dev/tty || true
  else
    tail -n 40 "$INSTALL_LOG_FILE" >&3 || true
  fi
}

ux_fail() {
  [[ "${UX_FAILED:-}" == "1" ]] && return 0
  UX_FAILED=1
  trap - ERR
  ux_heartbeat_stop || true
  if [[ -n "${UX_CURRENT_PHASE:-}" ]]; then
    ux_phase_set "$UX_CURRENT_PHASE" failed
  fi
  UX_PANEL_FROZEN=1
  UX_STATUS_STATIC=failed
  ux_redraw || true
  ux_printf '\n%sERROR%s  %s\n' "$C_RED" "$C_RESET" "$*"
  if [[ -n "${INSTALL_LOG_FILE:-}" && -f "$INSTALL_LOG_FILE" ]]; then
    ux_printf '%s--- last 40 lines ---%s\n' "$C_DIM" "$C_RESET"
    ux_tail_log
    ux_printf '%sFull log:%s %s\n' "$C_DIM" "$C_RESET" "$INSTALL_LOG_FILE"
  fi
}

ux_on_err() {
  local code="${1:-1}"
  trap - ERR
  ux_fail "install stopped (exit ${code})" || true
  exit "$code"
}

ux_step_begin() {
  local step="$1" info phase prev g
  UX_LAST_STEP="$step"
  info="$(ux_phase_for_step "$step")"
  phase="${info%%|*}"
  if [[ -n "$phase" && "$phase" != "$info" && "$phase" != "${UX_CURRENT_PHASE:-}" ]]; then
    if [[ -n "${UX_CURRENT_PHASE:-}" ]]; then
      ux_phase_finish "$UX_CURRENT_PHASE"
    fi
    prev="${UX_CURRENT_PHASE:-0}"
    for ((g = prev + 1; g < phase; g++)); do
      if [[ "$(ux_phase_get "$g")" == "pending" ]]; then
        ux_phase_set "$g" skipped
      fi
    done
    UX_CURRENT_PHASE="$phase"
    ux_phase_begin "$phase"
  fi
  ux_set_status "$step" "$(ux_step_hint "$step")"
  ux_redraw
}

ux_step_end() {
  ux_set_status "${UX_LAST_STEP:-}" "$(ux_step_hint "${UX_LAST_STEP:-}")"
  ux_redraw
}

ux_wait_group_begin() {
  ux_set_status "${UX_LAST_STEP:-wait}" "Waiting for ${1}"
}

ux_wait_group_end() {
  ux_set_status "${UX_LAST_STEP:-}" "$(ux_step_hint "${UX_LAST_STEP:-}")"
}

ux_wait_one_begin() {
  ux_set_status "${UX_LAST_STEP:-wait}" "Waiting for ${1}"
}

ux_wait_one_end() {
  ux_set_status "${UX_LAST_STEP:-}" "$(ux_step_hint "${UX_LAST_STEP:-}")"
}

ux_finish_phases() {
  local p st
  ux_heartbeat_stop || true
  for ((p = 1; p <= UX_PHASE_TOTAL; p++)); do
    st="$(ux_phase_get "$p")"
    if [[ "$st" == "running" ]]; then
      ux_phase_finish "$p"
    fi
  done
  UX_PANEL_FROZEN=1
  UX_STATUS_STATIC=complete
  ux_redraw
}

ux_print_summary() {
  local end_epoch="${END_TIME:-$(date +%s)}"
  local end_ts wall install download
  end_ts="$(ux_format_ts "$end_epoch")"
  wall="${WALL_DURATION:-$((end_epoch - INSTALL_WALL_START_EPOCH))}"
  install="${INSTALL_DURATION:-$((end_epoch - INSTALL_WALL_START_EPOCH))}"
  download="${DOWNLOAD_DURATION:-0}"

  ux_puts ""
  ux_puts "$(ux_box_top "Install summary")"
  ux_puts "$(ux_box_row "$(printf '%-10s %s' "Started" "${INSTALL_WALL_START:-}")")"
  ux_puts "$(ux_box_row "$(printf '%-10s %s' "Finished" "$end_ts")")"
  ux_puts "$(ux_box_row "$(printf '%-10s %s' "Wall" "$(ux_fmt_duration "$wall")")")"
  if [[ "$download" -gt 0 ]]; then
    ux_puts "$(ux_box_row "$(printf '%-10s %s' "Download" "$(ux_fmt_duration "$download") (outside timer)")")"
    ux_puts "$(ux_box_row "$(printf '%-10s %s' "Install" "$(ux_fmt_duration "$install")")")"
  else
    ux_puts "$(ux_box_row "$(printf '%-10s %s' "Install" "$(ux_fmt_duration "$install")")")"
  fi
  if [[ -s "${INSTALL_TIMINGS_FILE:-}" ]]; then
    local slow_line
    while IFS=$'\t' read -r step secs; do
      slow_line="$(printf '%-10s %s %ss' "Slowest" "$step" "$secs")"
      ux_puts "$(ux_box_row "$slow_line")"
    done < <(sort -t$'\t' -k2 -nr "${INSTALL_TIMINGS_FILE}" | head -3 || true)
  fi
  if [[ "${DEMO_TOUR_FAILED:-false}" == "true" ]]; then
    ux_puts "$(ux_box_row "Demo tour: some checks did not pass (install OK)")"
  elif [[ "${RUN_DEMO_TOUR:-true}" == "true" && "${INSTALL_PROFILE:-fast}" == "fast" && "${INSTALL_EXAMPLES:-true}" == "true" ]]; then
    ux_puts "$(ux_box_row "Demo tour: completed")"
  fi
  ux_puts "$(ux_box_bottom)"
  ux_puts ""
}

ux_open_footer() {
  if [[ "${UX_FORCE_FD:-}" == "3" ]]; then
    install_print_access_footer >&3
  elif [[ -w /dev/tty ]]; then
    install_print_access_footer >/dev/tty
  else
    install_print_access_footer >&3
  fi
}

install_rich() {
  exec 3>&1
  install_log_setup_file_only

  export INSTALL_UX_RICH=true
  export ZELKOR_UX_WRAPPED=true
  export ZELKOR_REPO_ROOT

  INSTALL_WALL_START_EPOCH=$(date +%s)
  export START_TIME="$INSTALL_WALL_START_EPOCH"
  INSTALL_START_TIME="$START_TIME"
  export INSTALL_START_TIME
  INSTALL_WALL_START="$(ux_format_ts "$INSTALL_WALL_START_EPOCH")"

  UX_HEARTBEAT_PID=""
  UX_CURRENT_PHASE=""
  UX_LAST_STEP=""
  UX_PANEL_LINES=0
  UX_PANEL_FROZEN=0
  UX_FAILED=0

  ux_init_glyphs
  ux_init_colors
  ux_init_files
  UX_BANNER="$(ux_hr "$UX_H" 70)"
  UX_SUBRULE="  $(ux_hr "$UX_H" 66)"
  export UX_BANNER UX_SUBRULE

  ux_resolve_install_flags
  UX_PHASE_TOTAL="$(ux_phase_total)"
  if [[ "${INSTALL_PROFILE:-fast}" == "full" ]]; then
    ux_phase_set 1 skipped
  fi

  trap ux_cleanup EXIT
  trap 'ux_on_err $?' ERR

  ux_set_status "install" "starting"
  ux_redraw
  ux_spinner_start

  local_install_prepare_engine
  # shellcheck source=scripts/install-engine.sh
  source "$ZELKOR_REPO_ROOT/scripts/install-engine.sh"

  trap - ERR
  ux_finish_phases
  ux_print_summary
  ux_open_footer || true
}

install_main() {
  install_log_note_tty

  if [[ -z "${INSTALL_UX:-}" ]]; then
    if [[ "${INSTALL_STDOUT_IS_TTY}" == "1" && -z "${NO_COLOR:-}" ]]; then
      INSTALL_UX=rich
    else
      INSTALL_UX=plain
    fi
  fi

  if [[ "$INSTALL_UX" == "rich" ]] && ! install_log_enabled; then
    echo "[install] INSTALL_LOG_FILE is off; showing plain logs" >&2
    INSTALL_UX=plain
  fi
  export INSTALL_UX

  if [[ "$INSTALL_UX" == "plain" ]]; then
    install_log_setup
    local_install_prepare_engine
    exec "$ZELKOR_REPO_ROOT/scripts/install-engine.sh" "$@"
  fi

  install_rich "$@"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  install_main "$@"
fi
