#!/usr/bin/env bash
# Project-owned version bump for the release standard (see RELEASING.md).
#
# Usage: make bump VERSION=X.Y.Z   (or scripts/bump.sh X.Y.Z)
#
# Sets the version in src/monarch_cli/__init__.py and pyproject.toml, refreshes
# uv.lock, moves the Unreleased changelog entries into a dated section with a
# fresh empty Unreleased section, updates the comparison links, and commits
# "chore: release vX.Y.Z". The maintainer pushes that commit.
#
# It refuses a dirty tree, a branch other than main, an existing tag, or an
# empty Unreleased section (bash scripts/check-changelog.sh).
set -euo pipefail

fail() {
    printf 'Error: %s\n' "$*" >&2
    exit 1
}

version="${1:-}"
if [[ -z "$version" ]]; then
    fail "usage: make bump VERSION=X.Y.Z (or scripts/bump.sh X.Y.Z)"
fi
if [[ ! "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    fail "VERSION must be a plain semantic version (X.Y.Z); got '$version'."
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

branch="$(git branch --show-current)"
[[ "$branch" == "main" ]] || fail "release from a clean main, not '$branch'."

if [[ -n "$(git status --porcelain)" ]]; then
    git status --short >&2
    fail "the working tree is not clean; commit or stash first."
fi

if git rev-parse --verify --quiet "v${version}^{commit}" >/dev/null; then
    fail "tag v${version} already exists; pick the next version."
fi

# Refuses an empty Unreleased section before anything is rewritten.
bash scripts/check-changelog.sh

python3 - "$version" <<'PY'
import datetime
import re
import sys
from pathlib import Path

version = sys.argv[1]
today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()


def replace_once(path: str, pattern: str, replacement: str) -> None:
    text = Path(path).read_text(encoding="utf-8")
    new, count = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE)
    if count != 1:
        sys.exit(f"could not update {path}: pattern {pattern!r} matched {count} times")
    Path(path).write_text(new, encoding="utf-8")


replace_once(
    "src/monarch_cli/__init__.py",
    r'^__version__ = "[^"]+"$',
    f'__version__ = "{version}"',
)
replace_once("pyproject.toml", r'^version = "[^"]+"$', f'version = "{version}"')

changelog = Path("CHANGELOG.md")
text = changelog.read_text(encoding="utf-8")
unreleased = re.search(
    r"^## \[Unreleased\]\n(?P<body>.*?)(?=^## \[)", text, re.MULTILINE | re.DOTALL
)
if unreleased is None:
    sys.exit("CHANGELOG.md has no '## [Unreleased]' section")
body = unreleased.group("body").strip("\n")
new_section = f"## [Unreleased]\n\n## [{version}] - {today}\n"
if body:
    new_section += f"\n{body}\n"
new_section += "\n"
text = text[: unreleased.start()] + new_section + text[unreleased.end() :]

links = re.search(r"^\[Unreleased\]: (?P<url>\S+)$", text, re.MULTILINE)
if links is None:
    sys.exit("CHANGELOG.md has no '[Unreleased]:' comparison link")
previous = re.search(r"/compare/v(?P<version>[^./\s]+(?:\.\d+)*)\.\.\.HEAD$", links.group("url"))
if previous is None:
    sys.exit("could not read the previous version from the Unreleased comparison link")
previous_version = previous.group("version")
repo_url = links.group("url").split("/compare/")[0]
replacement = (
    f"[Unreleased]: {repo_url}/compare/v{version}...HEAD\n"
    f"[{version}]: {repo_url}/compare/v{previous_version}...v{version}"
)
text = text[: links.start()] + replacement + text[links.end() :]
changelog.write_text(text, encoding="utf-8")

print(f"Bumped to {version} ({today}); previous release: v{previous_version}")
PY

uv lock

git add -A
git commit -m "chore: release v${version}"

printf '\nCommitted: chore: release v%s\n' "$version"
cat <<EOF

Next steps (see RELEASING.md):
  git push
  make prepublish
  make release-dry
  make release
EOF
