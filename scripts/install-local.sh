#!/bin/sh
# Install this checkout with its tested runtime and complete locked dependency set.
set -eu
repo=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
python="$repo/.venv/bin/python"
if [ ! -x "$python" ]; then
  echo "Missing checkout Python; run uv sync --frozen --all-extras first." >&2
  exit 1
fi
constraints=$(mktemp)
trap 'rm -f "$constraints"' EXIT HUP INT TERM
cd "$repo"
uv export --frozen --no-dev --no-emit-project --format requirements-txt > "$constraints"
uv tool install --python "$python" --constraints "$constraints" "$@" "$repo"
