"""Release version consistency tests.

Guards against tag/artifact drift: ``scripts/release.sh`` derives the git tag
from ``monarch_cli.__version__`` while the built wheel and sdist take their
version from ``pyproject.toml`` (and ``uv.lock`` mirrors it). If these disagree,
a release would tag one version while publishing another.

Keep them in sync when bumping (see ``docs/RELEASING.md``, Step 1).
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from monarch_cli import __version__

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
UV_LOCK_PATH = REPO_ROOT / "uv.lock"


def _pyproject_version() -> str:
    with PYPROJECT_PATH.open("rb") as handle:
        return tomllib.load(handle)["project"]["version"]


def _lock_version() -> str:
    with UV_LOCK_PATH.open("rb") as handle:
        document = tomllib.load(handle)
    for package in document.get("package", []):
        if package.get("name") == "monarch-cli":
            return package["version"]
    raise AssertionError("monarch-cli entry not found in uv.lock")


def test_pyproject_version_matches_package_version() -> None:
    pyproject_version = _pyproject_version()
    assert pyproject_version == __version__, (
        "pyproject.toml [project].version "
        f"({pyproject_version!r}) must match monarch_cli.__version__ "
        f"({__version__!r}); the git tag comes from __init__.py but the built "
        "wheel/sdist version comes from pyproject.toml. See docs/RELEASING.md "
        "Step 1."
    )


def test_uv_lock_version_matches_package_version() -> None:
    lock_version = _lock_version()
    assert lock_version == __version__, (
        "uv.lock monarch-cli version "
        f"({lock_version!r}) must match monarch_cli.__version__ ({__version__!r}); "
        "run 'uv lock' after bumping pyproject.toml (see docs/RELEASING.md Step 1)."
    )
