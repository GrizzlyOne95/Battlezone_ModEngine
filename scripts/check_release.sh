#!/usr/bin/env bash
# Decide whether a workflow run should publish a GitHub release.
#
# Writes should_release=true|false and tag=<tag> to $GITHUB_OUTPUT.
#   - A pushed v* tag releases that tag.
#   - A push or manual run on main releases v<VERSION> when that tag does not
#     exist on origin yet (i.e. VERSION was bumped). Existing versions are
#     never re-released.
#   - Anything else (pull requests, other branches) does not release.
set -euo pipefail

output="${GITHUB_OUTPUT:-/dev/stdout}"
event="${EVENT_NAME:-}"
ref_type="${GITHUB_REF_TYPE:-}"
ref_name="${GITHUB_REF_NAME:-}"
ref="${GITHUB_REF:-}"

emit() {
  echo "should_release=$1" >> "$output"
  echo "tag=$2" >> "$output"
  echo "should_release=$1 tag=$2${3:+ ($3)}"
}

if [[ "$ref_type" == "tag" && "$ref_name" == v* ]]; then
  emit true "$ref_name" "tag push"
  exit 0
fi

if [[ "$ref" != "refs/heads/main" || ( "$event" != "push" && "$event" != "workflow_dispatch" ) ]]; then
  emit false "" "not a push or manual run on main"
  exit 0
fi

version="$(tr -d '[:space:]' < VERSION)"
if [[ ! "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "::error::VERSION must look like 1.2.3, got '$version'" >&2
  exit 1
fi
tag="v$version"

# Exit code 2 means "no such ref"; any other failure must stop the run rather
# than guess, so a network error can never publish a duplicate release.
set +e
git ls-remote --exit-code --tags origin "refs/tags/$tag" > /dev/null
status=$?
set -e

case "$status" in
  0) emit false "$tag" "$tag already released" ;;
  2) emit true "$tag" "VERSION bumped to $version" ;;
  *) echo "::error::Could not query tags on origin (git exit $status)" >&2; exit "$status" ;;
esac
