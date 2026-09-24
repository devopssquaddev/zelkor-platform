#!/bin/sh
# Install runsc on the host and register the runsc containerd runtime.
# Runs inside a privileged pod with the host root mounted at /host.
set -eu

ROOT="${HOST_ROOT:-/host}"
GVISOR_RELEASE="${GVISOR_RELEASE:-20260817}"
GVISOR_BASE_URL="${GVISOR_BASE_URL:-https://storage.googleapis.com/gvisor/releases/release}"
VERIFY_CHECKSUM="${VERIFY_CHECKSUM:-false}"
DROP_IN_DIR="${DROP_IN_DIR:-}"
CONFIG_PATHS="${CONFIG_PATHS:-}"
RESTART_UNITS="${RESTART_UNITS:-}"

RUNSC_BLOCK='[plugins."io.containerd.grpc.v1.cri".containerd.runtimes.runsc]
  runtime_type = "io.containerd.runsc.v1"
[plugins."io.containerd.cri.v1.runtime".containerd.runtimes.runsc]
  runtime_type = "io.containerd.runsc.v1"
'

arch="$(chroot "${ROOT}" uname -m 2>/dev/null || uname -m)"
case "${arch}" in
  x86_64|amd64) arch=x86_64 ;;
  aarch64|arm64) arch=aarch64 ;;
  *)
    echo "unsupported architecture: ${arch}" >&2
    exit 1
    ;;
esac

runsc_configured() {
  _path="$1"
  [ -f "${_path}" ] && grep -q 'containerd.runtimes.runsc' "${_path}"
}

binaries_ready() {
  [ -x "${ROOT}/usr/local/bin/runsc" ] \
    && [ -x "${ROOT}/usr/local/bin/containerd-shim-runsc-v1" ] \
    && chroot "${ROOT}" /usr/local/bin/runsc --version 2>/dev/null | grep -q "${GVISOR_RELEASE}"
}

k3s_or_rke2_present() {
  [ -d "${ROOT}/var/lib/rancher/k3s" ] || [ -d "${ROOT}/var/lib/rancher/rke2" ]
}

collect_config_paths() {
  if [ -n "${CONFIG_PATHS}" ]; then
    for _p in ${CONFIG_PATHS}; do
      [ -f "${ROOT}${_p}" ] && printf '%s\n' "${ROOT}${_p}"
    done
    return 0
  fi
  if ! k3s_or_rke2_present; then
    [ -f "${ROOT}/etc/containerd/config.toml" ] && printf '%s\n' "${ROOT}/etc/containerd/config.toml"
  fi
  for _p in \
    "${ROOT}/var/lib/rancher/k3s/agent/etc/containerd/config.toml" \
    "${ROOT}/var/lib/rancher/k3s/agent/etc/containerd/config.toml.tmpl" \
    "${ROOT}/var/lib/rancher/k3s/server/etc/containerd/config.toml" \
    "${ROOT}/var/lib/rancher/k3s/server/etc/containerd/config.toml.tmpl" \
    "${ROOT}/var/lib/rancher/rke2/agent/etc/containerd/config.toml" \
    "${ROOT}/var/lib/rancher/rke2/agent/etc/containerd/config.toml.tmpl" \
    "${ROOT}/var/lib/rancher/rke2/server/etc/containerd/config.toml" \
    "${ROOT}/var/lib/rancher/rke2/server/etc/containerd/config.toml.tmpl"
  do
    [ -f "${_p}" ] && printf '%s\n' "${_p}"
  done
}

imports_drop_in_dir() {
  _cfg="$1"
  _line="$(grep '^imports' "${_cfg}" 2>/dev/null | head -1 || true)"
  [ -n "${_line}" ] || return 1
  _dir="$(printf '%s\n' "${_line}" | sed -n 's/.*\["\([^"]*\)\/\*\.toml".*/\1/p')"
  [ -n "${_dir}" ] || return 1
  printf '%s\n' "${ROOT}${_dir#${ROOT}}"
}

drop_in_dir() {
  if [ -n "${DROP_IN_DIR}" ]; then
    printf '%s\n' "${ROOT}${DROP_IN_DIR}"
    return 0
  fi
  for _cfg in $(collect_config_paths); do
    _dir="$(imports_drop_in_dir "${_cfg}" 2>/dev/null || true)"
    if [ -n "${_dir}" ]; then
      mkdir -p "${_dir}"
      printf '%s\n' "${_dir}"
      return 0
    fi
  done
  if [ -d "${ROOT}/etc/k0s/containerd.d" ]; then
    printf '%s\n' "${ROOT}/etc/k0s/containerd.d"
    return 0
  fi
  if [ -f "${ROOT}/etc/containerd/config.toml" ]; then
    _dir="$(imports_drop_in_dir "${ROOT}/etc/containerd/config.toml" 2>/dev/null || true)"
    if [ -n "${_dir}" ]; then
      mkdir -p "${_dir}"
      printf '%s\n' "${_dir}"
      return 0
    fi
    if grep -q 'config.d' "${ROOT}/etc/containerd/config.toml" 2>/dev/null; then
      mkdir -p "${ROOT}/etc/containerd/config.d"
      printf '%s\n' "${ROOT}/etc/containerd/config.d"
      return 0
    fi
  fi
  return 1
}

runtime_registered() {
  _drop="$(drop_in_dir 2>/dev/null || true)"
  if [ -n "${_drop}" ]; then
    runsc_configured "${_drop}/99-zelkor-runsc.toml"
    return $?
  fi
  for _cfg in $(collect_config_paths); do
    if runsc_configured "${_cfg}"; then
      return 0
    fi
  done
  return 1
}

if binaries_ready && runtime_registered; then
  echo "gVisor ${GVISOR_RELEASE} already installed and registered on this node"
  exit 0
fi

base="${GVISOR_BASE_URL%/}/${GVISOR_RELEASE}/${arch}"

verify_gvisor_bin() {
  _bin="$1"
  _host_path="$2"
  [ "${VERIFY_CHECKSUM}" = "true" ] || return 0
  _expected="$(curl -fsSL "${base}/${_bin}.sha512" | awk '{print $1}')"
  [ -n "${_expected}" ] || {
    echo "gVisor checksum file missing for ${_bin}" >&2
    return 1
  }
  _actual="$(chroot "${ROOT}" sha512sum "${_host_path}" | awk '{print $1}')"
  if [ "${_expected}" != "${_actual}" ]; then
    echo "gVisor checksum mismatch for ${_bin}" >&2
    return 1
  fi
}

for bin in runsc containerd-shim-runsc-v1; do
  curl -fsSL "${base}/${bin}" -o "${ROOT}/usr/local/bin/${bin}.new"
  verify_gvisor_bin "${bin}" "/usr/local/bin/${bin}.new"
  mv -f "${ROOT}/usr/local/bin/${bin}.new" "${ROOT}/usr/local/bin/${bin}"
done
chmod a+rx "${ROOT}/usr/local/bin/runsc" "${ROOT}/usr/local/bin/containerd-shim-runsc-v1"
chroot "${ROOT}" /usr/local/bin/runsc --version

needs_restart=0
_drop_dir="$(drop_in_dir 2>/dev/null || true)"
if [ -n "${_drop_dir}" ]; then
  _drop_file="${_drop_dir}/99-zelkor-runsc.toml"
  if ! runsc_configured "${_drop_file}"; then
    mkdir -p "${_drop_dir}"
    printf '%s\n' "${RUNSC_BLOCK}" > "${_drop_file}.new"
    mv -f "${_drop_file}.new" "${_drop_file}"
    needs_restart=1
  fi
else
  for cfg in $(collect_config_paths); do
    if ! runsc_configured "${cfg}"; then
      printf '\n%s\n' "${RUNSC_BLOCK}" >> "${cfg}"
      needs_restart=1
    fi
  done
fi

if ! runtime_registered && [ "${needs_restart}" -eq 0 ]; then
  echo "no containerd config found under ${ROOT}; installed binaries only" >&2
fi

restart_unit() {
  _unit="$1"
  if chroot "${ROOT}" systemctl is-active --quiet "${_unit}" 2>/dev/null; then
    chroot "${ROOT}" systemctl restart "${_unit}"
    return 0
  fi
  return 1
}

if [ "${needs_restart}" -eq 1 ]; then
  restarted=0
  if [ -n "${RESTART_UNITS}" ]; then
    for unit in ${RESTART_UNITS}; do
      if restart_unit "${unit}"; then
        restarted=1
        break
      fi
    done
  else
    for unit in k3s-agent k3s rke2-agent rke2-server containerd; do
      if restart_unit "${unit}"; then
        restarted=1
        break
      fi
    done
  fi
  if [ "${restarted}" -eq 0 ]; then
    echo "installed runsc but could not restart containerd/k3s/rke2" >&2
    exit 1
  fi
  sleep 5
fi

if ! runtime_registered; then
  echo "runsc binaries installed but containerd runtime not registered" >&2
  exit 1
fi

echo "gVisor ${GVISOR_RELEASE} installed on $(chroot "${ROOT}" hostname 2>/dev/null || echo unknown)"
