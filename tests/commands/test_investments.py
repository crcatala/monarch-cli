"""CLI contract tests for investment holdings."""

from __future__ import annotations

import json
from unittest.mock import patch

from typer.testing import CliRunner

from monarch_cli.commands.investments import app

runner = CliRunner()


def test_json_and_options_are_forwarded() -> None:
    payload = [{"account_id": "a", "quantity": None}]
    with patch(
        "monarch_cli.commands.investments.get_investment_holdings", return_value=payload
    ) as get:
        result = runner.invoke(app, ["--account", "a", "--aggregate", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == payload
    get.assert_called_once_with(["a"], include_hidden=False, aggregate=True, raw=False)


def test_raw_json_is_object_envelope() -> None:
    payload = {"a": {"portfolio": None}}
    with patch("monarch_cli.commands.investments.get_investment_holdings", return_value=payload):
        result = runner.invoke(app, ["--raw", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == payload


def test_help_documents_bounded_reads_and_raw() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "four" in result.stdout
    assert "raw" in result.stdout.lower()
