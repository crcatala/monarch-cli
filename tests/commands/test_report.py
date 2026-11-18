"""Saved report CLI contracts; no live mutations."""

import json
from unittest.mock import AsyncMock, patch

import pytest
from typer.testing import CliRunner

from monarch_cli.main import app

runner = CliRunner()
URL = "https://app.monarch.com/reports/cash-flow?tags=253277239843441604"


@pytest.mark.parametrize(
    "command,args,method,expected",
    [
        ("list", [], "list_reports", []),
        ("show", ["r1"], "show_report", {"id": "r1"}),
    ],
)
def test_read_commands(command, args, method, expected):
    with (
        patch("monarch_cli.commands.report.get_authenticated_client"),
        patch(
            f"monarch_cli.commands.report.{method}", new_callable=AsyncMock, return_value=expected
        ),
    ):
        result = runner.invoke(app, ["report", command, *args, "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == expected


def test_create_url_preview_without_authentication():
    with patch("monarch_cli.commands.report.get_authenticated_client") as get_client:
        result = runner.invoke(
            app, ["report", "create", "--name", "Trip", "--url", URL, "--dry-run", "--json"]
        )
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert data["status"] == "dry_run"
    assert data["input"]["transactionFilters"]["tags"] == ["253277239843441604"]
    get_client.assert_not_called()


@pytest.mark.parametrize(
    "args", [["--name", " "], ["--name", "Example", "--url", URL + "&unsupported=1"]]
)
def test_create_validates_before_auth(args):
    with patch("monarch_cli.commands.report.get_authenticated_client") as get_client:
        result = runner.invoke(app, ["report", "create", *args, "--json"])
    assert result.exit_code == 2
    assert json.loads(result.stdout)["error"] is True
    get_client.assert_not_called()


@pytest.mark.parametrize("content", ["not json", "[]", '{"tags": "1"}'])
def test_invalid_filter_file(tmp_path, content):
    path = tmp_path / "filters.json"
    path.write_text(content)
    with patch("monarch_cli.commands.report.get_authenticated_client") as get_client:
        result = runner.invoke(
            app, ["report", "create", "--name", "Example", "--filters-file", str(path), "--json"]
        )
    assert result.exit_code == 2
    get_client.assert_not_called()


def test_configuration_files(tmp_path):
    filters = tmp_path / "filters.json"
    filters.write_text('{"tags": ["1"]}')
    view = tmp_path / "view.json"
    view.write_text('{"analysisScope": "spending", "chartType": "pie"}')
    result = runner.invoke(
        app,
        [
            "report",
            "create",
            "--name",
            "Example",
            "--filters-file",
            str(filters),
            "--view-file",
            str(view),
            "--dry-run",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["input"]["reportView"]["analysisScope"] == "spending"


def test_delete_requires_yes_before_authentication():
    with patch("monarch_cli.commands.report.get_authenticated_client") as get_client:
        result = runner.invoke(app, ["--non-interactive", "report", "delete", "r1", "--json"])
    assert result.exit_code == 2
    assert "--yes" in json.loads(result.stdout)["message"]
    get_client.assert_not_called()


@pytest.mark.parametrize(
    "command,args,method",
    [
        ("create", ["--name", "Example", "--url", URL], "create_report"),
        ("rename", ["r1", "--name", "New"], "rename_report"),
        ("delete", ["r1", "--yes"], "delete_report"),
        ("delete", ["r1", "--dry-run"], "delete_report"),
    ],
)
def test_write_commands_no_automatic_retries(command, args, method):
    from monarch_cli.core.async_utils import run_api_call

    with (
        patch("monarch_cli.commands.report.get_authenticated_client"),
        patch(
            f"monarch_cli.commands.report.{method}",
            new_callable=AsyncMock,
            return_value={"status": "ok"},
        ),
        patch("monarch_cli.commands.report.run_api_call", wraps=run_api_call) as run,
    ):
        result = runner.invoke(app, ["report", command, *args, "--json"])
    assert result.exit_code == 0, result.output
    assert run.call_args.kwargs["max_retries"] == 0


def test_timeout_is_not_retried():
    with (
        patch("monarch_cli.commands.report.get_authenticated_client"),
        patch(
            "monarch_cli.commands.report.create_report",
            new_callable=AsyncMock,
            side_effect=TimeoutError,
        ) as create,
    ):
        result = runner.invoke(app, ["report", "create", "--name", "Example", "--json"])
    assert result.exit_code == 1
    assert "before retrying" in json.loads(result.stdout)["message"]
    assert create.await_count == 1


def test_filter_file_rejects_duplicate_keys(tmp_path):
    path = tmp_path / "filters.json"
    path.write_text('{"tags": ["1"], "tags": []}')
    result = runner.invoke(
        app,
        [
            "report",
            "create",
            "--name",
            "Example",
            "--filters-file",
            str(path),
            "--dry-run",
            "--json",
        ],
    )
    assert result.exit_code == 2
