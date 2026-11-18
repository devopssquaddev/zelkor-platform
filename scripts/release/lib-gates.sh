# shellcheck shell=bash disable=SC2034  # settings are read by the sourcing gate scripts
# CE-19g shared helpers for the kind gates (sourced by upgrade_gate.sh / retry_storm_gate.sh).
# kind install via ./install.sh --profile=perimeter (docs/agent-install.md); the provider is
# mock_llm.py in-cluster, wired as the vLLM backend. Every kubectl/helm call names the context.

GATE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GATE_REL="$GATE_ROOT/scripts/release"
GATE_TH="$GATE_REL/gate-thresholds.json"
GATE_CTX="${KUBECONTEXT:-kind-zelkor}"
# install.sh installs into the kube context's namespace (no -n), which is `default` on kind.
GATE_NS="${ZELKOR_NAMESPACE:-default}"
GATE_RELEASE="${HELM_RELEASE_NAME:-zelkor-platform}"
GATE_OUT="${GATE_OUT:-$GATE_ROOT/gate-results}"
GATEWAY_URL="${GATEWAY_BASE_URL:-http://127.0.0.1:8088}/v1/chat/completions"
# Host and consumer key of the kind overlay profiles/values-local-perimeter.yaml (CI cluster only).
GATEWAY_HOST="${AI_GATEWAY_HOST_HEADER:-ai-gateway.localhost}"
GATEWAY_KEY="${AI_GATEWAY_API_KEY:-dev-key}"
MOCK_NS="llm-mock"

export ZELKOR_NAMESPACE="$GATE_NS" INSTALL_UX=plain INSTALL_EXAMPLES=false RUN_DEMO_TOUR=false
export VLLM_BACKEND_URL="http://mock-llm.${MOCK_NS}.svc.cluster.local:8000/v1"

kube() { kubectl --context "$GATE_CTX" "$@"; }
hlm() { helm --kube-context "$GATE_CTX" "$@"; }
log() { echo "[gate $(date -u +%H:%M:%S)] $*" >&2; }

# th SECTION KEY -> value from gate-thresholds.json
th() {
  python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]][sys.argv[3]])' "$GATE_TH" "$1" "$2"
}

loadgen() {
  python3 "$GATE_REL/loadgen.py" --url "$GATEWAY_URL" --host "$GATEWAY_HOST" --key "$GATEWAY_KEY" "$@"
}

install_platform() {
  log "install.sh --profile=perimeter from $1"
  (cd "$1" && ./install.sh --profile=perimeter)
}

deploy_mock_provider() {
  log "deploy mock provider in namespace ${MOCK_NS}"
  kube create namespace "$MOCK_NS" --dry-run=client -o yaml | kube apply -f -
  kube -n "$MOCK_NS" create configmap mock-llm --from-file=mock_llm.py="$GATE_REL/mock_llm.py" \
    --dry-run=client -o yaml | kube apply -f -
  kube -n "$MOCK_NS" apply -f "$GATE_REL/mock-llm.yaml"
  kube -n "$MOCK_NS" rollout status deploy/mock-llm --timeout=300s
}

# write_result GATE RC DETAIL_JSON... -> $GATE_OUT/GATE.json (+ step summary line)
write_result() {
  local gate="$1" rc="$2"; shift 2
  python3 - "$GATE_OUT/$gate.json" "$gate" "$rc" "$@" <<'PY'
import json, sys
out, gate, rc, *details = sys.argv[1:]
doc = {"gate": gate, "pass": rc == "0", "details": {}}
for d in details:
    key, _, path = d.partition("=")
    try:
        doc["details"][key] = json.load(open(path))
    except (OSError, ValueError):
        doc["details"][key] = path
json.dump(doc, open(out, "w"), indent=2)
print(f"{gate}: {'PASS' if doc['pass'] else 'FAIL'}")
PY
  if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
    echo "- ${gate}: $([[ "$rc" == 0 ]] && echo PASS || echo FAIL)" >> "$GITHUB_STEP_SUMMARY"
  fi
}
