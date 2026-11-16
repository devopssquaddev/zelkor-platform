#!/usr/bin/env bash
# CE-19b round trip: cosign-verify every artifact in a release manifest with the identity the
# chart policy and `zelkor verify` use. The identity is read from the chart defaults
# (security.imageVerification.keyless), its one source.
#
# Usage: scripts/release/verify_artifacts.sh dist/release-manifest.json
# Checks per image: signature + slsaprovenance1 + spdxjson. Per chart: signature + slsaprovenance1;
# the platform chart also carries the release manifest attestation.

set -euo pipefail

manifest="${1:?usage: verify_artifacts.sh release-manifest.json}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RELEASE_TYPE="https://zelkor.io/attestations/release/v1"

command -v cosign >/dev/null || { echo "verify_artifacts: cosign not on PATH" >&2; exit 1; }

identity="$(python3 - "$ROOT/charts/zelkor-platform/values.yaml" <<'PY'
import sys, yaml
k = yaml.safe_load(open(sys.argv[1]))["security"]["imageVerification"]["keyless"]
print(k["issuer"])
print(k["subjectRegExp"])
PY
)"
issuer="$(sed -n 1p <<<"$identity")"
subject="$(sed -n 2p <<<"$identity")"
[[ -n "$issuer" && -n "$subject" ]] || { echo "verify_artifacts: empty identity in chart values" >&2; exit 1; }

failed=0
check() {
  local ref="$1"; shift
  if cosign "$@" --certificate-oidc-issuer "$issuer" --certificate-identity-regexp "$subject" "$ref" >/dev/null; then
    echo "PASS $* $ref"
  else
    echo "FAIL $* $ref"
    failed=$((failed + 1))
  fi
}

images="$(python3 -c 'import json,sys; [print(i["ref"].rsplit(":",1)[0]+"@"+i["digest"]) for i in json.load(open(sys.argv[1]))["images"]]' "$manifest")"
charts="$(python3 -c 'import json,sys; [print(c["name"]+" "+c["ref"]+"@"+c["digest"]) for c in json.load(open(sys.argv[1]))["charts"]]' "$manifest")"
[[ -n "$images" ]] || { echo "verify_artifacts: manifest lists no images" >&2; exit 1; }

while read -r ref; do
  check "$ref" verify
  check "$ref" verify-attestation --type slsaprovenance1
  check "$ref" verify-attestation --type spdxjson
done <<<"$images"

while read -r name ref; do
  [[ -n "$ref" ]] || continue
  check "$ref" verify
  check "$ref" verify-attestation --type slsaprovenance1
  if [[ "$name" == zelkor-platform ]]; then
    check "$ref" verify-attestation --type "$RELEASE_TYPE"
  fi
done <<<"$charts"

if (( failed > 0 )); then
  echo "verify_artifacts: ${failed} check(s) failed" >&2
  exit 1
fi
echo "verify_artifacts: all signatures and attestations verified"
