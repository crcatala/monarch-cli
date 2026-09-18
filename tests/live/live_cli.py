"""Shared subprocess boundary for the live test suites (mc-3437 / mc-584r).

This module is the single installed-console-script runner used by both the
read-only live smoke suite and the gated live mutation contract suite. There
is deliberately no second general runner: every live suite invoking the CLI
goes through :func:`run_cli`.

Boundary rules (mc-584r owner-approved refinement):

- Resolve the platform-appropriate ``monarch`` entry point from the scripts
  directory of the Python environment running pytest (derived from
  ``sys.executable``) and invoke it directly with ``shell=False``.
- Fail closed with setup guidance when that entry point is absent. Never
  silently fall back to a bare PATH command, a globally installed CLI, Typer
  ``CliRunner``, or a different environment. ``uv run --no-sync monarch`` is
  documented as a manual fallback, not this suite's subprocess boundary.
- Space consecutive API calls with :func:`_wait_for_api_throttle` so a local
  run stays below the service's throttling threshold.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


class InstalledCLINotFoundError(RuntimeError):
    """The installed ``monarch`` console script could not be resolved."""


# Configurable delay between API calls (seconds).  A one-second default keeps
# local runs below the API's throttling threshold without making CI opt in.
LIVE_DELAY = float(os.environ.get("MONARCH_LIVE_DELAY", "1.0"))
_last_call_at: float | None = None

#: Whether the ordinary read-only live suite was explicitly opted in.
LIVE_ENABLED = os.environ.get("MONARCH_LIVE_TESTS") == "1"

#: Default per-subprocess timeout for ordinary read-only live calls.
DEFAULT_TIMEOUT_SECONDS = 30


def resolve_monarch_executable(python_executable: str | None = None) -> str:
    """Resolve the installed ``monarch`` console script next to the interpreter.

    Args:
        python_executable: Override for ``sys.executable`` (used by tests).

    Returns:
        Absolute path to the installed console script.

    Raises:
        InstalledCLINotFoundError: If the entry point is absent. The message
            includes setup guidance and never suggests a silent fallback.
    """
    # Use abspath, not resolve(): a venv interpreter (e.g. ``.venv/bin/python``)
    # is commonly a symlink to a base interpreter. Following that symlink would
    # look for ``monarch`` in the base interpreter's scripts directory instead
    # of the environment that actually installed the console script, causing a
    # spurious fail-closed error for a correctly installed CLI.
    interpreter = Path(os.path.abspath(python_executable or sys.executable))
    scripts_dir = interpreter.parent
    script_name = "monarch.exe" if sys.platform == "win32" else "monarch"
    candidate = scripts_dir / script_name
    if not candidate.is_file():
        raise InstalledCLINotFoundError(
            "The installed 'monarch' console script was not found at "
            f"{candidate}. Install the project into the active environment "
            "(e.g. `uv sync --all-extras`) and run the suite with that "
            "environment's Python so the entry point exists. Do not fall back "
            "to a globally installed CLI or Typer CliRunner."
        )
    return str(candidate)


def _wait_for_api_throttle() -> None:
    """Wait between subprocess calls so consecutive API requests are spaced."""
    global _last_call_at
    if _last_call_at is not None and LIVE_DELAY > 0:
        elapsed = time.monotonic() - _last_call_at
        if elapsed < LIVE_DELAY:
            time.sleep(LIVE_DELAY - elapsed)
    _last_call_at = time.monotonic()


def run_cli(
    *args: str,
    check: bool = True,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[str]:
    """Run the installed ``monarch`` CLI and return the completed process.

    Args:
        *args: Command arguments (e.g. "accounts", "list", "--json"). Global
            options such as ``--allow-mutations`` must appear first.
        check: If True, raise ``pytest.fail`` on a non-zero exit code.
        timeout: Bounded subprocess timeout in seconds.

    Returns:
        CompletedProcess with stdout, stderr, returncode.
    """
    cmd = [resolve_monarch_executable(), *args]
    _wait_for_api_throttle()
    result = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=timeout)

    if check and result.returncode != 0:
        # Lazy import keeps this module importable outside pytest.
        import pytest

        pytest.fail(
            f"Command failed: {' '.join(cmd)}\n"
            f"Exit code: {result.returncode}\n"
            f"Stdout: {result.stdout}\n"
            f"Stderr: {result.stderr}"
        )

    return result


def run_cli_json(*args: str, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> Any:
    """Run the CLI with ``--json`` appended and parse the stdout JSON payload."""
    result = run_cli(*args, "--json", timeout=timeout)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        import pytest

        pytest.fail(f"Invalid JSON output: {e}\nOutput: {result.stdout}")


def get_output(result: subprocess.CompletedProcess[str]) -> str:
    """Get combined stdout + stderr for human-readable command output.

    Some commands output styled text to stderr (via Rich console).
    """
    return result.stdout + result.stderr
