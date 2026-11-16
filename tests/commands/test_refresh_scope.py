from unittest.mock import patch

from typer.testing import CliRunner

from monarch_cli.commands.accounts import app


def test_refresh_active_linked_scope():
    accounts = [
        {"id": "live", "is_active": True, "is_manual": False},
        {"id": "manual", "is_active": True, "is_manual": True},
        {"id": "closed", "is_active": False, "is_manual": False},
    ]
    with (
        patch("monarch_cli.commands.accounts.list_accounts", return_value=accounts),
        patch(
            "monarch_cli.commands.accounts.refresh_accounts", return_value={"status": "ok"}
        ) as refresh,
    ):
        result = CliRunner().invoke(app, ["refresh", "--active-linked", "--json"])
    assert result.exit_code == 0, result.output
    refresh.assert_called_once_with(["live"])


def test_refresh_status_active_linked_scope():
    accounts = [
        {"id": "live", "is_active": True, "is_manual": False},
        {"id": "manual", "is_active": True, "is_manual": True},
    ]
    with (
        patch("monarch_cli.commands.accounts.list_accounts", return_value=accounts),
        patch("monarch_cli.commands.accounts.get_authenticated_client"),
        patch("monarch_cli.commands.accounts.run_api_call", return_value=True),
    ):
        result = CliRunner().invoke(app, ["refresh-status", "--active-linked", "--json"])
    assert result.exit_code == 0, result.output
    assert "live" in result.output and "manual" not in result.output


def test_empty_scope_never_refreshes_all():
    with (
        patch("monarch_cli.commands.accounts.list_accounts", return_value=[]),
        patch("monarch_cli.commands.accounts.refresh_accounts") as refresh,
    ):
        result = CliRunner().invoke(app, ["refresh", "--active-linked", "--json"])
    assert result.exit_code != 0
    refresh.assert_not_called()


def test_explicit_and_active_scope_conflict():
    with patch("monarch_cli.commands.accounts.refresh_accounts") as refresh:
        result = CliRunner().invoke(app, ["refresh", "--active-linked", "-a", "live"])
    assert result.exit_code != 0
    refresh.assert_not_called()
