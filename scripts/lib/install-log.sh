# Install log routing. Sourced by install entry points.
# Not a customer entry point.
#
# install_log_note_tty must run before any stdout redirect: after a tee,
# stdout is a pipe and [[ -t 1 ]] is false.
# install_log_setup tees to the terminal (plain, production, quickstart).
# install_log_setup_file_only keeps engine output in the log file (rich local UX).

install_log_note_tty() {
  if [[ -n "${INSTALL_STDOUT_IS_TTY:-}" ]]; then
    return 0
  fi
  if [[ -t 1 ]]; then
    INSTALL_STDOUT_IS_TTY=1
  else
    INSTALL_STDOUT_IS_TTY=0
  fi
  export INSTALL_STDOUT_IS_TTY
}

install_log_enabled() {
  INSTALL_LOG_FILE="${INSTALL_LOG_FILE:-/tmp/zelkor-install.log}"
  [[ "$INSTALL_LOG_FILE" != "off" && "$INSTALL_LOG_FILE" != "false" ]]
}

install_log_setup() {
  install_log_note_tty
  if install_log_enabled; then
    : > "$INSTALL_LOG_FILE"
    exec > >(tee -a "$INSTALL_LOG_FILE") 2>&1
    echo "[install] logging to ${INSTALL_LOG_FILE}"
  fi
}

install_log_setup_file_only() {
  install_log_note_tty
  if ! install_log_enabled; then
    return 1
  fi
  if ! : > "$INSTALL_LOG_FILE"; then
    echo "[install] ERROR: cannot write ${INSTALL_LOG_FILE}" >&2
    return 1
  fi
  exec >>"$INSTALL_LOG_FILE" 2>&1
  echo "[install] logging to ${INSTALL_LOG_FILE}"
}
