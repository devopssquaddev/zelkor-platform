# Tee install stdout/stderr to a file. Sourced by install entry points.
# Not a customer entry point.

install_log_setup() {
  INSTALL_LOG_FILE="${INSTALL_LOG_FILE:-/tmp/zelkor-install.log}"
  if [[ "$INSTALL_LOG_FILE" != "off" && "$INSTALL_LOG_FILE" != "false" ]]; then
    : > "$INSTALL_LOG_FILE"
    exec > >(tee -a "$INSTALL_LOG_FILE") 2>&1
    echo "[install] logging to ${INSTALL_LOG_FILE}"
  fi
}
