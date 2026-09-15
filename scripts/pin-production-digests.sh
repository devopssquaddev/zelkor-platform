#!/usr/bin/env bash
# Resolve GHCR digests for first-party images and write them into
# profiles/values-production.yaml. Run after IMAGE_TAG push.
#
# Usage (from repo root):
#   IMAGE_TAG=1.1.1 ./scripts/pin-production-digests.sh
#
# Env:
#   IMAGE_REGISTRY  default ghcr.io/devopssquaddev
#   IMAGE_TAG       default 1.1.1
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

IMAGE_REGISTRY="${IMAGE_REGISTRY:-ghcr.io/devopssquaddev}"
IMAGE_TAG="${IMAGE_TAG:-1.1.1}"
OVERLAY="${OVERLAY:-$ROOT/profiles/values-production.yaml}"

digest_of() {
  local ref="$1"
  docker buildx imagetools inspect "$ref" | awk '/^Digest:/ { print $2; exit }'
}

need() {
  local name="$1"
  local ref="${IMAGE_REGISTRY}/${name}:${IMAGE_TAG}"
  local d
  d="$(digest_of "$ref")"
  [[ "$d" == sha256:* ]] || { echo "pin-production-digests: bad digest for ${ref}: ${d}" >&2; exit 1; }
  printf '%s' "$d"
}

AEGRA="$(need zelkor-aegra)"
AEGRA_CLI="$(need zelkor-aegra-cli)"
GUARDRAILS="$(need zelkor-guardrails)"
MCP="$(need zelkor-mcp)"
WORKER="$(need zelkor-sandbox-worker)"
SEED="$(need zelkor-langfuse-seed)"

python3 - "$OVERLAY" "$IMAGE_TAG" "$AEGRA" "$AEGRA_CLI" "$GUARDRAILS" "$MCP" "$WORKER" "$SEED" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
tag = sys.argv[2]
aegra, aegra_cli, guardrails, mcp, worker, seed = sys.argv[3:9]
text = path.read_text(encoding="utf-8")
needles = [
    (f"aegra:\n  image:\n    tag: \"{tag}\"\n    digest: \"", aegra),
    (f"  cli:\n    image:\n      tag: \"{tag}\"\n      digest: \"", aegra_cli),
    (f"guardrails:\n  nemo:\n    image:\n      tag: \"{tag}\"\n      digest: \"", guardrails),
    (f"mcp:\n  image:\n    tag: \"{tag}\"\n    digest: \"", mcp),
    (f"    workerImage:\n      tag: \"{tag}\"\n      digest: \"", worker),
    (f"  surfaces:\n    image:\n      tag: \"{tag}\"\n      digest: \"", seed),
]
out = text
for prefix, digest in needles:
  start = out.find(prefix)
  if start < 0:
    raise SystemExit(f"pin-production-digests: block not found:\n{prefix}")
  insert = start + len(prefix)
  end = out.find('"', insert)
  if end < 0:
    raise SystemExit("pin-production-digests: missing closing quote after digest")
  out = out[:insert] + digest + out[end:]
path.write_text(out, encoding="utf-8")
print(f"wrote digests into {path}")
PY
