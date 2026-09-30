# Default first-party GHCR tag = Chart.yaml appVersion (last lockstep CE release).
# Override with IMAGE_TAG=dev when iterating on unreleased local builds.
zelkor_chart_app_version() {
  local chart="${1:-${ZELKOR_REPO_ROOT:-.}/charts/zelkor-platform/Chart.yaml}"
  awk '/^appVersion:/ { gsub(/["'\'' ]/, "", $2); print $2; exit }' "$chart"
}
