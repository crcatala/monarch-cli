"""Tests for transaction summary and recurring commands."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from monarch_cli.commands.transactions import app

runner = CliRunner()


@pytest.fixture
def client() -> MagicMock:
    return MagicMock()


def _patch_client(client: MagicMock):
    return (
        patch("monarch_cli.commands.transactions.get_authenticated_client", return_value=client),
        patch("monarch_cli.output.progress.is_interactive", return_value=False),
    )


def test_summary_calls_filterless_upstream_method(client: MagicMock) -> None:
    async def summary() -> dict:
        return {"aggregates": {"summary": {"count": 2, "avg": -5, "sum": -10}}}

    client.get_transactions_summary = summary
    with _patch_client(client)[0], _patch_client(client)[1]:
        result = runner.invoke(app, ["summary", "--json"])

    assert result.exit_code == 0, result.stderr
    assert json.loads(result.stdout)["count"] == 2


def test_summary_does_not_accept_unsupported_dates() -> None:
    result = runner.invoke(app, ["summary", "--start", "2024-01-01"])
    assert result.exit_code != 0
    assert "No such option" in result.output


def test_recurring_without_dates_uses_client_current_month_default(client: MagicMock) -> None:
    captured: dict[str, str | None] = {}

    async def recurring(**kwargs):
        captured.update(kwargs)
        return {"recurringTransactionItems": []}

    client.get_recurring_transactions = recurring
    with _patch_client(client)[0], _patch_client(client)[1]:
        result = runner.invoke(app, ["recurring", "--json"])

    assert result.exit_code == 0, result.stderr
    assert captured == {"start_date": None, "end_date": None}
    assert json.loads(result.stdout) == []


def test_recurring_preset_passes_both_dates(client: MagicMock) -> None:
    captured: dict[str, str | None] = {}

    async def recurring(**kwargs):
        captured.update(kwargs)
        return {"recurringTransactionItems": []}

    client.get_recurring_transactions = recurring
    with _patch_client(client)[0], _patch_client(client)[1]:
        result = runner.invoke(app, ["recurring", "--preset", "this-month", "--json"])

    assert result.exit_code == 0, result.stderr
    assert captured["start_date"] is not None
    assert captured["end_date"] is not None


@pytest.mark.parametrize(
    "args",
    [
        ["--start", "2024-01-01"],
        ["--end", "2024-01-31"],
        ["--start", "not-a-date", "--end", "2024-01-31"],
        ["--start", "2024-02-01", "--end", "2024-01-31"],
    ],
)
def test_recurring_invalid_ranges_fail_before_client_creation(args: list[str]) -> None:
    with patch("monarch_cli.commands.transactions.get_authenticated_client") as get_client:
        result = runner.invoke(app, ["recurring", *args, "--json"])

    assert result.exit_code != 0
    get_client.assert_not_called()


def test_recurring_raw_preserves_upstream_response(client: MagicMock) -> None:
    raw = {"recurringTransactionItems": None, "futureField": "kept"}

    async def recurring(**_kwargs):
        return raw

    client.get_recurring_transactions = recurring
    with _patch_client(client)[0], _patch_client(client)[1]:
        result = runner.invoke(app, ["recurring", "--raw", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == raw
