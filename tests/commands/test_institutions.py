"""CLI tests for institution and subscription read surfaces."""

from __future__ import annotations

import json
from unittest.mock import patch

from typer.testing import CliRunner

from monarch_cli.main import app

runner = CliRunner()


def test_institutions_json_excludes_deleted_by_default() -> None:
    normalized = [
        {
            "credential_id": "cred-1",
            "provider": "PLAID",
            "institution_id": "inst-1",
            "institution_name": "Bank",
            "update_required": None,
            "disconnected": None,
            "disconnected_at": None,
            "last_updated": None,
            "issue": None,
            "balance_status": None,
            "transaction_status": None,
            "accounts": [],
        }
    ]
    with patch("monarch_cli.commands.institutions.list_institutions", return_value=normalized):
        result = runner.invoke(app, ["institutions", "list", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == normalized


def test_institutions_include_deleted_is_forwarded() -> None:
    with patch("monarch_cli.commands.institutions.list_institutions", return_value=[]) as list_cmd:
        result = runner.invoke(app, ["institutions", "list", "--include-deleted", "--json"])
    assert result.exit_code == 0
    list_cmd.assert_called_once()
    assert list_cmd.call_args.kwargs["include_deleted"] is True


def test_institutions_raw_preserves_upstream_fragment() -> None:
    raw = {
        "credentials": [],
        "accounts": [],
        "subscription": {"paymentSource": "card", "referralCode": "ref"},
    }
    with patch("monarch_cli.commands.institutions.get_institutions_raw", return_value=raw):
        result = runner.invoke(app, ["institutions", "list", "--raw", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == raw


def test_subscription_json_has_distinct_unavailable_state() -> None:
    normalized = {
        "available": False,
        "is_on_free_trial": None,
        "has_premium_entitlement": None,
    }
    with patch("monarch_cli.commands.subscription.show_subscription", return_value=normalized):
        result = runner.invoke(app, ["subscription", "show", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == normalized


def test_subscription_raw_preserves_sensitive_upstream_fields_explicitly() -> None:
    raw = {
        "subscription": {
            "paymentSource": "card",
            "referralCode": "ref",
            "isOnFreeTrial": False,
            "hasPremiumEntitlement": True,
        }
    }
    with patch("monarch_cli.commands.subscription.get_subscription_raw", return_value=raw):
        result = runner.invoke(app, ["subscription", "show", "--raw", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == raw


def test_raw_and_include_deleted_are_incompatible() -> None:
    """--raw passes the upstream response through, so --include-deleted is rejected."""
    with patch("monarch_cli.commands.institutions.get_institutions_raw") as raw:
        result = runner.invoke(
            app, ["institutions", "list", "--raw", "--include-deleted", "--json"]
        )
    assert result.exit_code == 2
    assert json.loads(result.stderr)["code"] == "INVALID_INPUT"
    raw.assert_not_called()
