"""Release-standard version line and ``update`` command tests.

These cover the CLI wiring only: the ``--version`` shape and the flags the
``update`` command passes to :mod:`monarch_cli.cli_meta`. The install-method
detection and the actual upgrade commands live in ``cli_meta`` and are not
invoked here (a test must never change the developer's installation).
"""

from __future__ import annotations

import re
from typing import Any

import pytest
from typer.testing import CliRunner

from monarch_cli import __version__, cli_meta
from monarch_cli.main import app

runner = CliRunner()

ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")

#: A wide terminal keeps help text from wrapping option names.
_HELP_ENV = {"COLUMNS": "200", "NO_COLOR": "1", "TERM": "dumb"}

#: The release-standard version line: ``monarch X.Y.Z (sha7[-dirty] YYYY-MM-DD)``.
VERSION_LINE_RE = re.compile(
    r"^monarch (?P<version>\d+\.\d+\.\d+) "
    r"\((?P<sha>[0-9a-f]{7})(?P<dirty>-dirty)? (?P<date>\d{4}-\d{2}-\d{2})\)$"
)


class TestVersionLine:
    @pytest.mark.parametrize(
        ("info", "expected"),
        [
            ({"version": "1.4.2"}, "mytool 1.4.2"),
            (
                {"version": "1.4.2", "commit": "a1b2c3d4e5", "date": "2026-10-27"},
                "mytool 1.4.2 (a1b2c3d 2026-10-27)",
            ),
            (
                {
                    "version": "1.4.3",
                    "commit": "9f8e7d6c5b",
                    "date": "2026-10-28",
                    "dirty": True,
                },
                "mytool 1.4.3 (9f8e7d6-dirty 2026-10-28)",
            ),
        ],
    )
    def test_format_version(self, info: dict[str, Any], expected: str) -> None:
        assert cli_meta.format_version("mytool", info) == expected

    def test_version_line_uses_build_info(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            cli_meta,
            "build_info",
            lambda _dist: {"version": "1.2.3", "commit": "abcdef0123", "date": "2026-01-02"},
        )
        assert cli_meta.version_line("monarch", "monarch-cli") == (
            "monarch 1.2.3 (abcdef0 2026-01-02)"
        )

    def test_cli_version_prints_the_standard_line(self) -> None:
        result = runner.invoke(app, ["--version"])

        assert result.exit_code == 0, result.output
        line = result.output.strip()
        match = VERSION_LINE_RE.match(line)
        assert match is not None, line
        assert match.group("version") == __version__


class TestUpdateCommand:
    def test_check_passes_the_installed_package_and_exit_code(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: dict[str, Any] = {}

        def fake_run_update(
            name: str, dist: str, *, check: bool = False, force: bool = False
        ) -> int:
            calls.update({"name": name, "dist": dist, "check": check, "force": force})
            return 1

        monkeypatch.setattr(cli_meta, "run_update", fake_run_update)

        result = runner.invoke(app, ["update", "--check"])

        assert result.exit_code == 1, result.output
        assert calls == {
            "name": "monarch",
            "dist": "monarch-cli",
            "check": True,
            "force": False,
        }

    def test_update_and_force_reach_run_update(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[dict[str, Any]] = []

        def fake_run_update(
            name: str, dist: str, *, check: bool = False, force: bool = False
        ) -> int:
            calls.append({"name": name, "dist": dist, "check": check, "force": force})
            return 0

        monkeypatch.setattr(cli_meta, "run_update", fake_run_update)

        assert runner.invoke(app, ["update"]).exit_code == 0
        assert runner.invoke(app, ["update", "--force"]).exit_code == 0
        assert [call["force"] for call in calls] == [False, True]
        assert all(call["check"] is False for call in calls)

    def test_help_documents_check_and_force(self) -> None:
        result = runner.invoke(app, ["update", "--help"], env=_HELP_ENV)

        assert result.exit_code == 0, result.output
        output = ANSI_ESCAPE_RE.sub("", result.output)
        assert "--check" in output
        assert "--force" in output
