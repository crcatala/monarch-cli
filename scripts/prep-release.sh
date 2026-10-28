#!/usr/bin/env bash
# release-standard: scripts/prep-release.sh r1 (do not edit; see RELEASING.md)
# Usage: scripts/prep-release.sh [last-tag]
# Prints a changelog-drafting prompt, then the commits and files changed since the last tag.
set -euo pipefail

# Only version tags (vX.Y.Z) mark releases; other tags never become the range start.
last_tag="${1:-$(git describe --tags --abbrev=0 --match 'v[0-9]*' 2>/dev/null || true)}"
if [[ -n "$last_tag" ]] && ! git rev-parse --verify --quiet "${last_tag}^{commit}" >/dev/null; then
  echo "Error: '$last_tag' is not a valid tag or commit." >&2
  exit 1
fi

range='HEAD'
[[ -n "$last_tag" ]] && range="${last_tag}..HEAD"

echo '=== Release Prep ==='
if [[ -n "$last_tag" ]]; then echo "Changes since: $last_tag"; else echo 'No prior tag; showing all commits.'; fi
echo

# Prompt first, so everything below it can be copied into an LLM in one go.
cat <<'EOF'
=== Changelog prompt (copy everything below this line) ===

Draft Keep a Changelog entries for the Unreleased section from the commits below.
Include only user-facing changes. Group items under Added, Changed, Fixed, Removed,
or Security; omit empty groups. Exclude internal tests, CI, refactors, and routine
dependency updates unless users are affected. Keep each item to one line and keep
PR or issue numbers in parentheses where the commits mention them.

=== Full commit messages ===
EOF

# Drop co-author trailers (any case). awk, not sed's GNU-only `I` flag, so this runs on macOS too.
git log "$range" --format='## %s%n%n%b%n---' --no-merges | awk 'tolower($0) !~ /^co-authored-by:/' | cat -s

echo
echo '=== Changed files ==='
if [[ -n "$last_tag" ]]; then
  git diff --stat "$range"
else
  # Compare against the empty tree so a first release shows everything.
  git diff --stat "$(git hash-object -t tree /dev/null)" HEAD
fi
