"""Unit tests for the shared installed-CLI resolver (mc-584r).

These are ordinary, non-live tests: they never spawn a subprocess or call the
Monarch API, so they run in the default ``-m "not live"`` suite. They pin the
contract that both live suites (read-only and gated mutation) depend on: the
``monarch`` console script is resolved from the scripts directory of the
*pytest* environment, without following a venv interpreter symlink out of that
environment, and the resolver fails closed when the entry point is absent.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.live import live_cli as live


def _monarch_name() -> str:
    return "monarch.exe" if live.sys.platform == "win32" else "monarch"


def test_resolve_finds_console_script_next_to_interpreter(tmp_path: Path) -> None:
    scripts_dir = tmp_path / "bin"
    scripts_dir.mkdir()
    interpreter = scripts_dir / "python"
    interpreter.write_text("")
    script = scripts_dir / _monarch_name()
    script.write_text("")

    assert live.resolve_monarch_executable(str(interpreter)) == str(script)


def test_resolve_uses_venv_dir_when_interpreter_is_a_symlink(tmp_path: Path) -> None:
    # A venv interpreter is typically a symlink to a base interpreter. The CLI
    # must be resolved from the venv's scripts directory (where it was
    # installed), not from the symlink target's directory.
    venv_bin = tmp_path / "venv" / "bin"
    venv_bin.mkdir(parents=True)
    base_bin = tmp_path / "base" / "bin"
    base_bin.mkdir(parents=True)

    base_python = base_bin / "python3.13"
    base_python.write_text("")

    venv_python = venv_bin / "python"
    venv_python.symlink_to(base_python)
    venv_script = venv_bin / _monarch_name()
    venv_script.write_text("")

    assert live.resolve_monarch_executable(str(venv_python)) == str(venv_script)


def test_resolve_fails_closed_when_console_script_absent(tmp_path: Path) -> None:
    scripts_dir = tmp_path / "bin"
    scripts_dir.mkdir()
    interpreter = scripts_dir / "python"
    interpreter.write_text("")

    with pytest.raises(live.InstalledCLINotFoundError):
        live.resolve_monarch_executable(str(interpreter))


def test_resolve_fails_closed_when_symlink_target_has_script(tmp_path: Path) -> None:
    # A decoy ``monarch`` in the symlink target's directory must not be used:
    # only the pytest environment's scripts directory is authoritative.
    venv_bin = tmp_path / "venv" / "bin"
    venv_bin.mkdir(parents=True)
    base_bin = tmp_path / "base" / "bin"
    base_bin.mkdir(parents=True)

    base_python = base_bin / "python3.13"
    base_python.write_text("")
    (base_bin / _monarch_name()).write_text("")  # decoy, must be ignored

    venv_python = venv_bin / "python"
    venv_python.symlink_to(base_python)

    with pytest.raises(live.InstalledCLINotFoundError):
        live.resolve_monarch_executable(str(venv_python))
