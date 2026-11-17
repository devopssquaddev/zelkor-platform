#!/usr/bin/env bash
# CE-19g: attach gate results (pass or fail) to the GitHub release and summarise them.
# A missing gate result is reported as MISSING, never as a pass.
#
# Usage: scripts/release/publish_gates.sh vX.Y.Z-ce gate-results/

set -euo pipefail

tag="${1:?usage: publish_gates.sh TAG DIR}"
dir="${2:?usage: publish_gates.sh TAG DIR}"
summary="${GITHUB_STEP_SUMMARY:-/dev/stdout}"

{
  echo "## Release gates for ${tag}"
  for gate in upgrade-rollback retry-storm; do
    f="${dir}/${gate}.json"
    if [[ -f "$f" ]]; then
      echo "- ${gate}: $(python3 -c 'import json,sys; print("PASS" if json.load(open(sys.argv[1]))["pass"] else "FAIL")' "$f")"
    else
      echo "- ${gate}: MISSING"
    fi
  done
} >> "$summary"

shopt -s nullglob
files=("$dir"/*.json)
if (( ${#files[@]} == 0 )); then
  echo "::warning::no gate results to publish for ${tag}"
  exit 0
fi
if gh release view "$tag" --repo "$GITHUB_REPOSITORY" >/dev/null 2>&1; then
  gh release upload "$tag" "${files[@]}" --clobber --repo "$GITHUB_REPOSITORY"
else
  echo "::warning::release ${tag} does not exist yet; gate results stay in the workflow artifacts"
fi
