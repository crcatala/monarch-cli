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

# 1. Stamp the build info and build the wheel + sdist from the project
#    metadata. The stamp records HEAD, its commit date, and the dirty state, so
#    the installed wheel reports the same --version line as a checkout.
log "Stamping build info from HEAD"
python3 "$REPO_ROOT/scripts/build_info.py" "$REPO_ROOT/src/monarch_cli/_build_info.json"

log "Building distributions with uv build"
rm -rf "$DIST_DIR"
uv build --out-dir "$DIST_DIR" "$REPO_ROOT"

WHEEL="$(find "$DIST_DIR" -maxdepth 1 -name '*.whl' -print -quit)"
[[ -n "$WHEEL" ]] || fail "no wheel produced in ${DIST_DIR}"
log "Built wheel: $(basename "$WHEEL")"

# The stamp is generated inside src/ but must still be packaged: an installed
# copy reads it instead of git, so a wheel without it cannot report a commit.
log "Verifying the wheel ships the build stamp"
python3 - "$WHEEL" <<'PY'
import json
import sys
import zipfile

with zipfile.ZipFile(sys.argv[1]) as archive:
    names = [n for n in archive.namelist() if n.endswith("monarch_cli/_build_info.json")]
    if len(names) != 1:
        raise SystemExit(f"wheel has {len(names)} monarch_cli/_build_info.json entries")
    info = json.loads(archive.read(names[0]))
if not info.get("commit"):
    raise SystemExit("wheel build info has no commit; stamp before building")
print(f"  build info: {info['commit'][:7]} {info.get('date')} dirty={info.get('dirty')}")
PY

# The sdist is uploaded too, and a source install builds its wheel from it, so
# the stamp must be in the sdist as well.
SDIST="$(find "$DIST_DIR" -maxdepth 1 -name '*.tar.gz' -print -quit)"
[[ -n "$SDIST" ]] || fail "no sdist produced in ${DIST_DIR}"
log "Verifying the sdist ships the build stamp"
python3 - "$SDIST" <<'PY'
import json
import sys
import tarfile

with tarfile.open(sys.argv[1]) as archive:
    names = [n for n in archive.getnames() if n.endswith("monarch_cli/_build_info.json")]
    if len(names) != 1:
        raise SystemExit(f"sdist has {len(names)} monarch_cli/_build_info.json entries")
    info = json.load(archive.extractfile(names[0]))
if not info.get("commit"):
    raise SystemExit("sdist build info has no commit; stamp before building")
print(f"  sdist build info: {info['commit'][:7]}")
PY

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
from monarch_cli.schemas import SCHEMA_ARTIFACTS

location = pathlib.Path(monarch_cli.__file__).resolve()
print(f"monarch_cli imported from {location}")
if "site-packages" not in location.parts:
    raise SystemExit(f"monarch_cli resolved outside site-packages: {location}")

# Packaged schema artifacts must ship in the wheel and stay loadable.
for artifact in SCHEMA_ARTIFACTS.values():
    document = artifact.load()
    if document.get("$id") != artifact.urn:
        raise SystemExit(f"schema {artifact.resource} has an unexpected $id")
print(f"loaded {len(SCHEMA_ARTIFACTS)} packaged schema artifacts")
PY

# 6. Both console entry points must run from the installed wheel, and both
#    must print the release-standard version line for the stamped commit.
log "Invoking console entry points"
for entrypoint in monarch monarch-cli; do
    bin_path="$ENTRYPOINT_DIR/$entrypoint"
    [[ -x "$bin_path" ]] || fail "missing console script: ${entrypoint}"

    env -u VIRTUAL_ENV -u PYTHONPATH "$bin_path" --help > "$WORKDIR/${entrypoint}-help.txt" \
        || fail "${entrypoint} --help failed"
    env -u VIRTUAL_ENV -u PYTHONPATH "$bin_path" --version > "$WORKDIR/${entrypoint}-version.txt" \
        || fail "${entrypoint} --version failed"

    python3 - "$REPO_ROOT" "$WORKDIR/${entrypoint}-version.txt" "$entrypoint" <<'PY'
import json
import subprocess
import sys
import tomllib
from pathlib import Path

repo, version_file, entrypoint = sys.argv[1:4]
version = tomllib.loads((Path(repo) / "pyproject.toml").read_text())["project"]["version"]
stamp = json.loads((Path(repo) / "src/monarch_cli/_build_info.json").read_text())
line = Path(version_file).read_text().strip()

if stamp.get("commit"):
    sha = stamp["commit"][:7] + ("-dirty" if stamp.get("dirty") else "")
    expected = f"monarch {version} ({sha} {stamp['date']})"
else:
    expected = f"monarch {version}"
if line != expected:
    raise SystemExit(f"{entrypoint} --version: expected {expected!r}, got {line!r}")

# The stamp's dirty flag must match the tree; a release build is clean, so a
# -dirty line there is a failure rather than a warning.
dirty = bool(
    subprocess.run(
        ["git", "-C", repo, "status", "--porcelain"], capture_output=True, text=True, check=True
    ).stdout.strip()
)
if dirty != bool(stamp.get("dirty")):
    raise SystemExit(
        f"build stamp dirty={stamp.get('dirty')} but the tree dirty state is {dirty}; rerun"
    )
print(f"  {entrypoint:<12} --help OK, --version: {line}")
PY
done

log "smoke-install OK"
