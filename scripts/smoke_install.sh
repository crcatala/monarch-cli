#!/usr/bin/env bash
#
# Canonical wheel smoke install for monarch-cli (mc-43s0).
#
# Builds the distributions, then installs the built wheel into a throwaway
# environment that lives OUTSIDE the source checkout, resolving dependencies
# only from the wheel's published metadata. Finally it invokes both console
# entry points so an incomplete or unresolvable release artifact fails here
# instead of in a consumer's environment.
#
# This is the single maintained implementation of that procedure: `make
# smoke-install`, CI, `make prepublish`, and scripts/release.sh all delegate to
# it instead of duplicating the steps.
#
# Environment overrides:
#   SMOKE_PYTHON  Python version for the isolated environment (default: 3.13)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SMOKE_PYTHON="${SMOKE_PYTHON:-3.13}"
DIST_DIR="${REPO_ROOT}/dist"

log() { printf '\n==> %s\n' "$*"; }

fail() {
    printf '\nERROR: %s\n' "$*" >&2
    exit 1
}

# 1. Build the wheel + sdist from the project metadata.
log "Building distributions with uv build"
rm -rf "$DIST_DIR"
uv build --out-dir "$DIST_DIR" "$REPO_ROOT"

WHEEL="$(find "$DIST_DIR" -maxdepth 1 -name '*.whl' -print -quit)"
[[ -n "$WHEEL" ]] || fail "no wheel produced in ${DIST_DIR}"
log "Built wheel: $(basename "$WHEEL")"

# 2. Create an isolated environment outside the source checkout. Nothing here
#    may see the repository's src/ tree or its development virtualenv.
WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/monarch-cli-smoke.XXXXXX")"
cleanup() { rm -rf "$WORKDIR"; }
trap cleanup EXIT

log "Creating isolated environment (Python ${SMOKE_PYTHON}) in ${WORKDIR}"
uv python install "$SMOKE_PYTHON"
uv venv --python "$SMOKE_PYTHON" "$WORKDIR/venv"

VENV_PYTHON="$WORKDIR/venv/bin/python"
ENTRYPOINT_DIR="$WORKDIR/venv/bin"

# 3. Install the wheel with no cache, no repository configuration, and no local
#    source overrides, so dependencies come strictly from wheel metadata.
log "Installing the wheel into the isolated environment"
INSTALL_LOG="$WORKDIR/install.log"
(
    cd "$WORKDIR"
    env -u VIRTUAL_ENV -u PYTHONPATH -u PYTHONSTARTUP \
        uv pip install \
        --python "$VENV_PYTHON" \
        --no-cache \
        --no-config \
        --no-sources \
        "$WHEEL"
) 2>&1 | tee "$INSTALL_LOG"

# 4. Dependency metadata must resolve cleanly: no missing-extra or conflict
#    warnings attributable to the project's own metadata.
log "Checking install output for metadata warnings"
if grep -Ei "extra .*(not provided|missing)|does not provide the extra|dependency conflict|incompatible" "$INSTALL_LOG"; then
    fail "install emitted dependency/extra warnings (see above)"
fi

# 5. Guard against accidental leakage of the source tree or dev environment.
log "Verifying the package resolves outside the source checkout"
env -u VIRTUAL_ENV -u PYTHONPATH "$VENV_PYTHON" - <<'PY'
import pathlib
import sys

import monarch_cli

location = pathlib.Path(monarch_cli.__file__).resolve()
print(f"monarch_cli imported from {location}")
if "site-packages" not in location.parts:
    raise SystemExit(f"monarch_cli resolved outside site-packages: {location}")
PY

# 6. Both console entry points must run from the installed wheel.
log "Invoking console entry points"
for entrypoint in monarch monarch-cli; do
    bin_path="$ENTRYPOINT_DIR/$entrypoint"
    [[ -x "$bin_path" ]] || fail "missing console script: ${entrypoint}"

    env -u VIRTUAL_ENV -u PYTHONPATH "$bin_path" --help > "$WORKDIR/${entrypoint}-help.txt" \
        || fail "${entrypoint} --help failed"
    env -u VIRTUAL_ENV -u PYTHONPATH "$bin_path" --version > "$WORKDIR/${entrypoint}-version.txt" \
        || fail "${entrypoint} --version failed"

    version_output="$(cat "$WORKDIR/${entrypoint}-version.txt")"
    [[ -n "$version_output" ]] || fail "${entrypoint} --version produced no output"
    printf '  %-12s --help OK, --version: %s\n' "$entrypoint" "$version_output"
done

log "smoke-install OK"
