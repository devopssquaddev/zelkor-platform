#!/usr/bin/env bash
# CE-19g gate 1: install N-1 on kind, upgrade to N, `helm rollback` to N-1, all while a fixed-rate
# load runs through the gateway. Any non-2xx or connection error fails the gate (published ceiling:
# gate-thresholds.json upgrade_rollback.max_failed_requests = 0).
#
# Usage: scripts/release/upgrade_gate.sh vX.Y.Z-ce     (run from a checkout of that tag, full history)

set -euo pipefail
# shellcheck source=lib-gates.sh source-path=SCRIPTDIR
source "$(dirname "${BASH_SOURCE[0]}")/lib-gates.sh"

NEW_TAG="${1:?usage: upgrade_gate.sh vX.Y.Z-ce}"
PREV_TAG="$(cd "$GATE_ROOT" && python3 "$GATE_REL/ce_tags.py" previous "$NEW_TAG")"
mkdir -p "$GATE_OUT"
prev_dir="$(mktemp -d)/prev"
stop="$GATE_OUT/upgrade-rollback.stop"
rm -f "$stop"
# shellcheck disable=SC2317,SC2329  # invoked by the EXIT trap (2317 in shellcheck <= 0.10)
cleanup() {
  touch "$stop"
  git -C "$GATE_ROOT" worktree remove --force "$prev_dir" >/dev/null 2>&1 || true
}
trap cleanup EXIT

log "N-1 ${PREV_TAG} -> N ${NEW_TAG} -> rollback"
git -C "$GATE_ROOT" worktree add --detach "$prev_dir" "$PREV_TAG"
install_platform "$prev_dir"
deploy_mock_provider
model="$(th upgrade_rollback model)"
loadgen --model "$model" --wait-ready "$(th upgrade_rollback ready_timeout_seconds)"
history="$(hlm -n "$GATE_NS" history "$GATE_RELEASE" -o json)" \
  || { log "helm release ${GATE_RELEASE} not found in namespace ${GATE_NS}"; exit 1; }
rev_prev="$(python3 -c 'import json,sys; print(json.load(sys.stdin)[-1]["revision"])' <<<"$history")"
settle="$(th upgrade_rollback settle_seconds)"

loadgen --model "$model" --rps "$(th upgrade_rollback rps)" --duration 86400 --until-file "$stop" \
  --max-failed "$(th upgrade_rollback max_failed_requests)" --out "$GATE_OUT/upgrade-rollback-load.json" &
load_pid=$!
sleep "$settle"

log "upgrade to ${NEW_TAG}"
install_platform "$GATE_ROOT"
sleep "$settle"

log "helm rollback ${GATE_RELEASE} to revision ${rev_prev} (${PREV_TAG})"
hlm -n "$GATE_NS" rollback "$GATE_RELEASE" "$rev_prev" --wait --timeout 10m
sleep "$settle"

touch "$stop"
rc=0
wait "$load_pid" || rc=$?
printf '{"from": "%s", "to": "%s", "rollback_revision": %s}\n' "$PREV_TAG" "$NEW_TAG" "$rev_prev" \
  > "$GATE_OUT/upgrade-rollback-path.json"
write_result upgrade-rollback "$rc" "path=$GATE_OUT/upgrade-rollback-path.json" \
  "load=$GATE_OUT/upgrade-rollback-load.json"
exit "$rc"
