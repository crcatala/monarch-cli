"""Installation must retain the tested runtime and locked dependencies."""

import os
import subprocess
from pathlib import Path


def test_install_uses_checkout_runtime_and_frozen_dependencies(tmp_path):
    repo = Path(__file__).resolve().parents[2]
    uv = tmp_path / "uv"
    log = tmp_path / "calls"
    uv.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$INSTALL_TEST_LOG"\n')
    uv.chmod(0o755)
    result = subprocess.run(
        ["sh", str(repo / "scripts/install-local.sh")],
        env={
            **os.environ,
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "INSTALL_TEST_LOG": str(log),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    calls = log.read_text().splitlines()
    assert "export --frozen --no-dev --no-emit-project" in calls[0]
    assert f"tool install --python {repo}/.venv/bin/python" in calls[1]
    assert "--constraints " in calls[1]
    assert calls[1].endswith(str(repo))


def test_install_stops_without_tested_runtime(tmp_path):
    repo = Path(__file__).resolve().parents[2]
    script = tmp_path / "scripts" / "install-local.sh"
    script.parent.mkdir()
    script.write_text((repo / "scripts/install-local.sh").read_text())
    result = subprocess.run(["sh", str(script)], capture_output=True, text=True, check=False)
    assert result.returncode == 1
    assert "Missing checkout Python" in result.stderr


def test_install_stops_when_locked_export_fails(tmp_path):
    repo = Path(__file__).resolve().parents[2]
    uv = tmp_path / "uv"
    log = tmp_path / "calls"
    uv.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$INSTALL_TEST_LOG"\nexit 42\n')
    uv.chmod(0o755)
    result = subprocess.run(
        ["sh", str(repo / "scripts/install-local.sh")],
        env={
            **os.environ,
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "INSTALL_TEST_LOG": str(log),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 42
    assert len(log.read_text().splitlines()) == 1
