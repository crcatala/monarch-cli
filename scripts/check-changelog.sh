#!/usr/bin/env bash
# release-standard: scripts/check-changelog.sh r1 (do not edit; see RELEASING.md)
# Fail a release when CHANGELOG.md has no unreleased user-facing entries.
set -euo pipefail

file="${1:-CHANGELOG.md}"
if [[ ! -f "$file" ]]; then
  echo "Error: $file not found." >&2
  exit 1
fi

content=$(awk '/^## \[Unreleased\]/{found=1; next} /^## \[/{exit} found{print}' "$file")
if ! awk '/^### /{section=1; next} section && /^[-*+] /{found=1} END{exit !found}' <<<"$content"; then
  echo "Error: $file has no unreleased user-facing entries." >&2
  echo 'Run the release prep script, then add a section under "## [Unreleased]", such as "### Added" followed by "- New feature".' >&2
  exit 1
fi

echo 'Changelog has unreleased entries.'
