#!/usr/bin/env bash
# Generate localSigning key material on the install host; pass to Helm only (--set / --set-file).
set -euo pipefail

_local_signing_log() {
  printf '%s\n' "$*" >&2
}

_local_signing_python() {
  if [[ -n "${ZELKOR_PYTHON:-}" ]]; then
    printf '%s\n' "$ZELKOR_PYTHON"
    return 0
  fi
  local root="${ZELKOR_REPO_ROOT:-}"
  if [[ -n "$root" && -x "${root}/.venv/bin/python3" ]]; then
    printf '%s\n' "${root}/.venv/bin/python3"
    return 0
  fi
  if [[ -n "$root" && -x "${root}/.venv-install-host/bin/python3" ]]; then
    printf '%s\n' "${root}/.venv-install-host/bin/python3"
    return 0
  fi
  printf '%s\n' python3
}

_local_signing_python_usable() {
  local py="$1"
  if [[ "$py" == */* ]]; then
    [[ -x "$py" ]]
    return
  fi
  command -v "$py" >/dev/null 2>&1
}

_ensure_jwt_generate_host_venv() {
  local root="${ZELKOR_REPO_ROOT:-}"
  [[ -n "$root" ]] || return 1
  local venv="${root}/.venv-install-host"
  if [[ -x "${venv}/bin/python3" ]] && "${venv}/bin/python3" -c "import jwt, cryptography, yaml" >/dev/null 2>&1; then
    export ZELKOR_PYTHON="${venv}/bin/python3"
    return 0
  fi
  _local_signing_log "Creating install-host venv for localSigning (${venv})..."
  python3 -m venv "$venv"
  "${venv}/bin/pip" install -q --upgrade pip
  "${venv}/bin/pip" install -q \
    'PyJWT[crypto]>=2.8.0' 'cryptography>=42.0.0' 'PyYAML>=6.0'
  export ZELKOR_PYTHON="${venv}/bin/python3"
  "${venv}/bin/python3" -c "import jwt, cryptography, yaml"
}

_ensure_jwt_generate_deps() {
  local py
  py="$(_local_signing_python)"
  if "$py" -c "import jwt, cryptography, yaml" >/dev/null 2>&1; then
    return 0
  fi
  if _ensure_jwt_generate_host_venv; then
    return 0
  fi
  _local_signing_log "Installing PyJWT/cryptography/PyYAML for localSigning (${py})..."
  if "$py" -m pip install -q --disable-pip-version-check --user \
    'PyJWT[crypto]>=2.8.0' 'cryptography>=42.0.0' 'PyYAML>=6.0' 2>/dev/null; then
    :
  elif "$py" -m pip install -q --disable-pip-version-check --break-system-packages \
    'PyJWT[crypto]>=2.8.0' 'cryptography>=42.0.0' 'PyYAML>=6.0' 2>/dev/null; then
    :
  else
    return 1
  fi
  "$py" -c "import jwt, cryptography, yaml"
}

_local_signing_read_config() {
  local values_file="$1"
  local py
  _ensure_jwt_generate_deps
  py="$(_local_signing_python)"
  "$py" - "$values_file" <<'PY'
import json, sys
import yaml
path = sys.argv[1]
with open(path, encoding="utf-8") as f:
    data = yaml.safe_load(f) or {}
jwt = (data.get("platform") or {}).get("tenants", {}).get("jwt") or {}
ls = jwt.get("localSigning") or {}
if not ls.get("enabled"):
    raise SystemExit(0)
issuer = (jwt.get("issuer") or "").strip()
seed = (ls.get("seedTenant") or "").strip()
if not issuer or not seed:
    raise SystemExit("localSigning requires platform.tenants.jwt.issuer and localSigning.seedTenant")
out = {
    "issuer": issuer,
    "audiences": jwt.get("audiences") or ["zelkor"],
    "seedTenant": seed,
    "seedTokenTTL": ls.get("seedTokenTTL") or "24h",
    "rotationId": str(ls.get("rotationId") or "1"),
}
print(json.dumps(out))
PY
}

_local_signing_helm_sets_include() {
  local needle="$1"
  local arg
  for arg in "$@"; do
    [[ "$arg" == *"$needle"* ]] && return 0
  done
  return 1
}

# append_local_signing_helm_sets ARRAY_NAME VALUES_FILE
append_local_signing_helm_sets() {
  local arr_name="$1"
  local values_file="$2"
  local root="${ZELKOR_REPO_ROOT:-}"
  local release="${HELM_RELEASE_NAME:-zelkor-platform}"

  [[ -f "$values_file" ]] || return 0
  local py
  py="$(_local_signing_python)"
  if ! _local_signing_python_usable "$py"; then
    _local_signing_log "localSigning: Python not found (${py})"
    return 1
  fi

  local cfg
  if ! cfg="$(_local_signing_read_config "$values_file")"; then
    _local_signing_log "localSigning: failed to read ${values_file} (need PyYAML on the install host; pip installs automatically when pip is available)"
    return 1
  fi
  [[ -n "$cfg" ]] || return 0
  py="$(_local_signing_python)"
  [[ -n "$root" ]] || {
    _local_signing_log "localSigning: ZELKOR_REPO_ROOT required"
    return 1
  }

  local state_dir="${ZELKOR_JWT_STATE_DIR:-${HOME}/.cache/zelkor/${release}/jwt}"
  mkdir -p "$state_dir"

  local seed_token
  seed_token="$("$py" - "$root" "$state_dir" "$cfg" <<'PY'
import json, subprocess, sys
root, state_dir, cfg_json = sys.argv[1], sys.argv[2], sys.argv[3]
cfg = json.loads(cfg_json)
aud = json.dumps(cfg["audiences"])
base = [
    sys.executable, f"{root}/images/common/zelkor_jwt_generate.py",
    "--state-dir", state_dir,
    "--issuer", cfg["issuer"],
    "--audiences", aud,
    "--seed-tenant", cfg["seedTenant"],
    "--seed-ttl", cfg["seedTokenTTL"],
    "--rotation-id", cfg["rotationId"],
]
subprocess.check_call(base)
out = subprocess.check_output(base + ["--print-seed-token"], text=True)
sys.stdout.write(out.strip())
PY
)"

  _local_signing_log "localSigning: applying signing key + JWKS via Helm (no post-helm cluster writes)"
  # bash 3.2 (macOS) has no nameref; install hosts are bash 4+ but keep eval for portability.
  eval "${arr_name}+=(--set-file platform.tenants.jwt.localSigning.privateKey=${state_dir}/private.pem)"
  # .json set-file is parsed as a Helm object; use .txt so jwks stays a string value.
  eval "${arr_name}+=(--set-file platform.tenants.jwt.jwks=${state_dir}/jwks.txt)"
  eval "${arr_name}+=(--set-string platform.telemetry.langfuse.surfaces.tools.authToken=${seed_token})"
  eval "${arr_name}+=(--set platform.telemetry.langfuse.surfaces.tools.seedTenant=$("$py" -c 'import json,sys; print(json.loads(sys.argv[1])["seedTenant"])' "$cfg"))"
}

# Fail closed when the profile enables localSigning but Helm sets were not appended.
verify_local_signing_helm_sets() {
  local values_file="$1"
  shift
  local -a helm_args=("$@")
  [[ -f "$values_file" ]] || return 0
  local py cfg
  py="$(_local_signing_python)"
  _local_signing_python_usable "$py" || return 0
  if ! cfg="$(_local_signing_read_config "$values_file" 2>/dev/null)"; then
    return 0
  fi
  [[ -n "$cfg" ]] || return 0
  if _local_signing_helm_sets_include "platform.tenants.jwt.localSigning.privateKey" "${helm_args[@]}" \
    && _local_signing_helm_sets_include "platform.telemetry.langfuse.surfaces.tools.authToken" "${helm_args[@]}"; then
    return 0
  fi
  _local_signing_log "localSigning: profile enables localSigning but Helm did not receive signing key or Langfuse MCP authToken"
  return 1
}
