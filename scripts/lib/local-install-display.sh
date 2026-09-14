# Load local kind footer/credential hints from the active profile values file(s).
# Sourced by ./install.sh only — not used by production/quickstart installers.

local_install_display_values_files() {
  local root="${ZELKOR_REPO_ROOT:-.}"
  local profile="${INSTALL_PROFILE:-fast}"
  local primary="${VALUES_FILE:-}"
  if [[ -n "$primary" && -f "$root/$primary" ]]; then
    echo "$root/$primary"
    return 0
  fi
  case "$profile" in
    fast) echo "$root/profiles/values-local-fast.yaml" ;;
    full) echo "$root/profiles/values-local.yaml" ;;
    *) return 1 ;;
  esac
}

local_install_export_display_env() {
  local root="${ZELKOR_REPO_ROOT:-.}"
  local values_path
  values_path="$(local_install_display_values_files)" || return 0
  [[ -f "$values_path" ]] || return 0

  _local_install_yaml_kv() {
    local key="$1"
    grep -E "^[[:space:]]*${key}:" "$values_path" 2>/dev/null | head -1 | sed -E 's/^[^:]*:[[:space:]]*"?([^"#]*)"?.*/\1/' | tr -d '\r'
  }

  if ! command -v python3 >/dev/null 2>&1; then
    INSTALL_DISPLAY_LANGFUSE_ADMIN_EMAIL="$(_local_install_yaml_kv email)"
    INSTALL_DISPLAY_LANGFUSE_ADMIN_PASSWORD="$(_local_install_yaml_kv password)"
    INSTALL_DISPLAY_AI_GATEWAY_CONSUMER_KEY="$(_local_install_yaml_kv consumerKey)"
    export INSTALL_DISPLAY_LANGFUSE_ADMIN_EMAIL INSTALL_DISPLAY_LANGFUSE_ADMIN_PASSWORD INSTALL_DISPLAY_AI_GATEWAY_CONSUMER_KEY
    return 0
  fi

  # shellcheck disable=SC2016
  eval "$(VALUES_PATH="$values_path" python3 <<'PY'
import os, sys
try:
    import yaml
except ImportError:
    sys.exit(0)

path = os.environ["VALUES_PATH"]
with open(path, encoding="utf-8") as fh:
    doc = yaml.safe_load(fh) or {}

def get(*keys, default=""):
    cur = doc
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
    return cur if cur is not None else default

exports = {
    "INSTALL_DISPLAY_LANGFUSE_ADMIN_EMAIL": get("langfuse", "admin", "email"),
    "INSTALL_DISPLAY_LANGFUSE_ADMIN_PASSWORD": get("langfuse", "admin", "password"),
    "INSTALL_DISPLAY_LANGFUSE_PUBLIC_KEY": get("langfuse", "init", "projectPublicKey"),
    "INSTALL_DISPLAY_LANGFUSE_SECRET_KEY": get("langfuse", "init", "projectSecretKey"),
    "INSTALL_DISPLAY_LANGFUSE_ORG_ID": get("langfuse", "init", "orgId"),
    "INSTALL_DISPLAY_LANGFUSE_ORG_NAME": get("langfuse", "init", "orgName"),
    "INSTALL_DISPLAY_LANGFUSE_PROJECT_ID": get("langfuse", "init", "projectId"),
    "INSTALL_DISPLAY_LANGFUSE_PROJECT_NAME": get("langfuse", "init", "projectName"),
    "INSTALL_DISPLAY_POSTGRES_USER": get("postgresql", "auth", "username"),
    "INSTALL_DISPLAY_POSTGRES_PASSWORD": get("postgresql", "auth", "password"),
    "INSTALL_DISPLAY_POSTGRES_DATABASE": get("postgresql", "auth", "database"),
    "INSTALL_DISPLAY_AI_GATEWAY_CONSUMER_KEY": get("aiGateway", "consumerKey"),
    "INSTALL_DISPLAY_GATEWAY_LANGFUSE_HOST": get("gateway", "hosts", "langfuse"),
    "INSTALL_DISPLAY_GATEWAY_AGENTS_HOST": get("gateway", "hosts", "agents"),
    "INSTALL_DISPLAY_GATEWAY_AIGW_HOST": get("gateway", "hosts", "aiGateway"),
}

for key, val in exports.items():
    if val is None or val == "":
        continue
    safe = str(val).replace("\\", "\\\\").replace('"', '\\"')
    print(f'export {key}="{safe}"')
PY
)"
}
