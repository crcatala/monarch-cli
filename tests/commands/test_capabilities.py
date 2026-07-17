"""Tests for the machine-readable capabilities manifest."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from monarch_cli.core.config import reset_config
from monarch_cli.main import app
from monarch_cli.output import set_default_format
from monarch_cli.output.plain import reset_color_state

runner = CliRunner()


@pytest.fixture(autouse=True)
def reset_cli_state() -> None:
    reset_config()
    set_default_format(None)
    reset_color_state()


def test_capabilities_json_manifest_is_deterministic() -> None:
    first = runner.invoke(app, ["capabilities", "--json"])
    second = runner.invoke(app, ["capabilities", "--json"])

    assert first.exit_code == 0
    assert second.exit_code == 0
    assert first.stdout == second.stdout

    data = json.loads(first.stdout)
    assert data["contract_version"] == "1"
    assert data["cli_version"]
    assert data["exit_codes"] == {
        "0": "success",
        "1": "general error",
        "2": "usage error",
        "4": "input needed",
    }
    assert "MONARCH_TOKEN" in {env["name"] for env in data["env_vars"]}
    assert "config.toml" in {config["path"] for config in data["config_files"]}

    command_names = [command["name"] for command in data["commands"]]
    assert command_names == sorted(command_names)
    assert "auth login" in command_names
    assert "transactions list" in command_names
    assert "capabilities" in command_names

    auth_login = next(command for command in data["commands"] if command["name"] == "auth login")
    assert auth_login["mutates"] is True
    assert "--storage" in {flag for option in auth_login["flags"] for flag in option["flags"]}


def test_capabilities_plain_points_to_json() -> None:
    result = runner.invoke(app, ["capabilities"])

    assert result.exit_code == 0
    assert "Run `monarch capabilities --json`" in result.stderr
