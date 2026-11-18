#!/usr/bin/env bash
# Print the CHANGELOG.md section for a tag (e.g. v1.1.0); empty if none.
set -euo pipefail
tag="$1"
file="${2:-CHANGELOG.md}"
awk -v heading="## $tag" '
  $0 == heading { found = 1; next }
  found && /^## / { exit }
  found { print }
' "$file"
