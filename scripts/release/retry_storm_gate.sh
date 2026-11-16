#!/usr/bin/env bash
# CE-19g gate 2: a 30-minute retry storm against a provider that always fails (100% failures),
# sampling Envoy dataplane memory. Fails when any sample exceeds the published ceiling or memory
# is not flat (gate-thresholds.json retry_storm), or when any storm request succeeded.
#
# Usage: scripts/release/retry_storm_gate.sh vX.Y.Z-ce     (run from a checkout of that tag)

set -euo pipefail
# shellcheck source=lib-gates.sh source-path=SCRIPTDIR
source "$(dirname "${BASH_SOURCE[0]}")/lib-gates.sh"

TAG="${1:?usage: retry_storm_gate.sh vX.Y.Z-ce}"
mkdir -p "$GATE_OUT"
samples="$GATE_OUT/retry-storm-memory.csv"
stop="$GATE_OUT/retry-storm.stop"
rm -f "$stop"
: > "$samples"
trap 'touch "$stop"' EXIT

log "retry storm on ${TAG}"
install_platform "$GATE_ROOT"
deploy_mock_provider
loadgen --model "$(th upgrade_rollback model)" --wait-ready "$(th upgrade_rollback ready_timeout_seconds)"

interval="$(th retry_storm sample_interval_seconds)"
(
  while [[ ! -e "$stop" ]]; do
    python3 "$GATE_REL/gateway_memory.py" sample --context "$GATE_CTX" >> "$samples" || log "memory sample failed"
    sleep "$interval"
  done
) &
sampler_pid=$!

load_rc=0
loadgen --model "$(th retry_storm model)" --rps "$(th retry_storm rps)" --retries "$(th retry_storm client_retries)" \
  --duration "$(th retry_storm duration_seconds)" --max-ok 0 --out "$GATE_OUT/retry-storm-load.json" || load_rc=$?
touch "$stop"
wait "$sampler_pid" || true

mem_rc=0
python3 "$GATE_REL/gateway_memory.py" analyze --samples "$samples" --thresholds "$GATE_TH" \
  --out "$GATE_OUT/retry-storm-memory.json" || mem_rc=$?
rc=$(( load_rc != 0 || mem_rc != 0 ))
write_result retry-storm "$rc" "memory=$GATE_OUT/retry-storm-memory.json" "load=$GATE_OUT/retry-storm-load.json"
exit "$rc"
