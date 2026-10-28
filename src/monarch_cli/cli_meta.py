"""release-standard: cli_meta.py r2 (see the release standard before editing)

Version line and self-update for a Python CLI. Copy into the package, then (Typer):

    from . import cli_meta

    def _version(value: bool) -> None:
        if value:
            typer.echo(cli_meta.version_line("mytool", "my-dist"))
            raise typer.Exit()

    @app.command()
    def update(check: bool = False, force: bool = False) -> None:
        raise typer.Exit(cli_meta.run_update("mytool", "my-dist", check=check, force=force))

Pass published=False to run_update for a tool that is not on PyPI: it then never looks the name
up on PyPI (an unrelated package could have it) and only updates from the original source.

A built wheel carries _build_info.json next to this file (scripts/build_info.py). A run from a
git checkout (an editable install) reads git instead, so it always shows the current commit.
"""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.request
from importlib import metadata
from pathlib import Path
from typing import Any, cast

HERE = Path(__file__).resolve().parent


def _run(args: list[str], cwd: Path | None = None) -> str | None:
    try:
        return subprocess.run(
            args, cwd=cwd, capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


# ── version ─────────────────────────────────────────────────────────────────


def format_version(name: str, info: dict[str, Any]) -> str:
    if not info.get("commit"):
        return f"{name} {info['version']}"
    sha = info["commit"][:7] + ("-dirty" if info.get("dirty") else "")
    return (
        f"{name} {info['version']} ({sha} {info['date']})"
        if info.get("date")
        else f"{name} {info['version']} ({sha})"
    )


def checkout_root(package_dir: Path = HERE) -> Path | None:
    """The source checkout this module runs from, or None for an installed copy."""
    if "site-packages" in package_dir.parts or "dist-packages" in package_dir.parts:
        return None
    top = _run(["git", "rev-parse", "--show-toplevel"], cwd=package_dir)
    return Path(top) if top and (Path(top) / "pyproject.toml").exists() else None


def build_info(dist: str, package_dir: Path = HERE) -> dict[str, Any]:
    try:
        version = metadata.version(dist)
    except metadata.PackageNotFoundError:
        version = "unknown"
    info: dict[str, Any] = {"version": version}
    root = checkout_root(package_dir)
    stamp = package_dir / "_build_info.json"
    if not root and stamp.exists():
        try:
            return {**info, **json.loads(stamp.read_text())}
        except ValueError:
            pass
    commit = _run(["git", "rev-parse", "HEAD"], cwd=root) if root else None
    if commit:
        info["commit"] = commit
        info["date"] = _run(["git", "show", "-s", "--format=%cs", "HEAD"], cwd=root)
        info["dirty"] = _run(["git", "status", "--porcelain"], cwd=root) != ""
    return info


def version_line(name: str, dist: str) -> str:
    return format_version(name, build_info(dist))


# ── install detection ───────────────────────────────────────────────────────


def detect_install(package_dir: str, checkout: bool) -> str:
    if checkout:
        return "checkout"
    p = package_dir.replace("\\", "/")
    if "/uv/tools/" in p:
        return "uv"
    if "/mise/installs/pipx-" in p:
        return "mise"
    if "/pipx/venvs/" in p:
        return "pipx"
    if "/site-packages/" in p or "/dist-packages/" in p:
        return "pip"
    return "unknown"


def reinstall_checkout(
    root: Path, prefix: str = sys.prefix, python: str = sys.executable
) -> list[str]:
    """Reinstall an editable checkout with the installer that owns its environment, so dependency
    changes and the version in the installed metadata follow the pull."""
    p = prefix.replace("\\", "/")
    if "/uv/tools/" in p:
        return ["uv", "tool", "install", "--editable", str(root), "--reinstall"]
    if "/pipx/venvs/" in p:
        return ["pipx", "install", "--editable", str(root), "--force"]
    return [python, "-m", "pip", "install", "--editable", str(root)]


def update_steps(
    kind: str,
    dist: str,
    *,
    root: Path | None = None,
    published: bool = True,
    prefix: str = sys.prefix,
    python: str = sys.executable,
) -> list[list[str]] | None:
    if kind == "checkout":
        return (
            [["git", "pull", "--ff-only"], reinstall_checkout(root, prefix, python)]
            if root
            else None
        )
    # uv and pipx reinstall from the source recorded at install time; pip and mise would look the
    # name up on PyPI, which is wrong for an unpublished tool.
    steps = {
        "uv": [["uv", "tool", "upgrade", dist]],
        "pipx": [["pipx", "upgrade", dist]],
        "mise": [["mise", "upgrade", "--bump", f"pipx:{dist}"]] if published else None,
        "pip": [[python, "-m", "pip", "install", "--upgrade", dist]] if published else None,
    }
    return steps.get(kind)


# ── latest version ──────────────────────────────────────────────────────────


def compare_versions(a: str, b: str) -> int:
    """Negative when a < b. Plain X.Y.Z; a prerelease sorts before its release."""

    def parse(v: str) -> tuple[list[int], str | None]:
        core, _, pre = v.lstrip("v").partition("-")
        nums = [int(n) if n.isdigit() else 0 for n in core.split(".")[:3]]
        return nums + [0] * (3 - len(nums)), pre or None

    (x, xp), (y, yp) = parse(a), parse(b)
    if x != y:
        return -1 if x < y else 1
    if xp == yp:
        return 0
    if xp is None:
        return 1
    if yp is None:
        return -1
    return -1 if xp < yp else 1


def pypi_latest(dist: str) -> str | None:
    try:
        with urllib.request.urlopen(f"https://pypi.org/pypi/{dist}/json", timeout=10) as r:
            return cast(str, json.load(r)["info"]["version"])
    except (OSError, ValueError, KeyError):
        return None


def check_for_update(
    kind: str, dist: str, info: dict[str, Any], root: Path | None, published: bool = True
) -> dict[str, Any]:
    """{'current', 'latest', 'available' (None when unknown), 'reason'}."""
    if kind == "checkout" and root:
        if _run(["git", "fetch", "--quiet", "origin", "main"], cwd=root) is None:
            return {
                "current": info["version"],
                "available": None,
                "reason": "could not fetch origin/main",
            }
        behind = _run(["git", "rev-list", "--count", "HEAD..origin/main"], cwd=root)
        head = _run(["git", "rev-parse", "--short=7", "HEAD"], cwd=root)
        remote = _run(["git", "rev-parse", "--short=7", "origin/main"], cwd=root)
        return {"current": head, "latest": remote, "available": behind not in (None, "0")}
    if not published:
        reason = (
            "unpublished, so there is no version to compare; "
            "`update --force` reinstalls from the original source"
        )
        return {"current": info["version"], "available": None, "reason": reason}
    latest = pypi_latest(dist)
    if not latest:
        reason = "could not get the latest version from PyPI"
        return {"current": info["version"], "available": None, "reason": reason}
    return {
        "current": info["version"],
        "latest": latest,
        "available": compare_versions(info["version"], latest) < 0,
    }


# ── update command ──────────────────────────────────────────────────────────


def run_update(
    name: str, dist: str, check: bool = False, force: bool = False, published: bool = True
) -> int:
    """Exit code: see the release standard's update table."""
    root = checkout_root()
    kind = detect_install(str(HERE), root is not None)
    info = build_info(dist)
    status = check_for_update(kind, dist, info, root, published)

    if status["available"] is None:
        print(
            f"{name}: cannot tell whether an update is available ({status['reason']}).",
            file=sys.stderr,
        )
        if check or not force:
            return 2
    elif not status["available"] and not force:
        print(f"{name} is up to date ({status['current']}).")
        return 0
    elif status["available"]:
        print(f"{name}: update available, {status['current']} → {status['latest']}.")
    if check:
        return 1 if status["available"] else 0

    steps = update_steps(kind, dist, root=root, published=published)
    if steps is None:
        print(
            f"{name}: cannot update the install at {HERE} automatically ({kind}).", file=sys.stderr
        )
        print(
            f"Update it the way it was installed, for example `uv tool upgrade {dist}`.",
            file=sys.stderr,
        )
        return 1
    if kind == "checkout":
        branch = _run(["git", "symbolic-ref", "--quiet", "--short", "HEAD"], cwd=root)
        dirty = _run(["git", "status", "--porcelain"], cwd=root) != ""
        if branch != "main" or dirty:
            print(
                f"{name}: the checkout at {root} must be clean and on main to update.",
                file=sys.stderr,
            )
            return 1
    for step in steps:
        print("$ " + " ".join(step))
        try:
            code = subprocess.run(step, cwd=root if kind == "checkout" else None).returncode
        except OSError as e:
            print(f"{name}: could not run `{step[0]}` ({e.strerror or e}).", file=sys.stderr)
            return 1
        if code != 0:
            print(f"{name}: `{' '.join(step)}` failed.", file=sys.stderr)
            if kind == "checkout" and step[0] != "git":
                # The pull is done, so a plain retry would report "up to date"
                # and skip the reinstall.
                print(
                    f"Fix the cause, then run `{name} update --force` to finish the update.",
                    file=sys.stderr,
                )
            else:
                print(f"Fix the cause, then run `{name} update` again.", file=sys.stderr)
            return 1
    print(f"{name} updated. Check with `{name} --version`.")
    return 0
