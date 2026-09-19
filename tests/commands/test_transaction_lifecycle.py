"""Contract tests for safe manual transaction create/delete (mc-yqfi)."""

from __future__ import annotations

import json
import re
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from monarch_cli.commands.transactions import app
from monarch_cli.core.config import Config, reset_config, set_config
from monarch_cli.core.operations import (
    Effect,
    collect_command_effects,
    reset_mutation_authorization,
    set_mutation_authorized,
)
from monarch_cli.main import app as root_app

runner = CliRunner()

_ANSI = re.compile(r"\x1b\[[0-9;]*m")

CREATE_BASE = [
    "create",
    "--date",
    "2026-01-15",
    "--account-id",
    "ACC1",
    "--amount",
    "12.34",
    "--merchant",
    "Coffee Shop",
    "--category-id",
    "CAT1",
]
DELETE_BASE = ["delete", "--transaction-id", "txn-1"]


def _plain(text: str) -> str:
    return _ANSI.sub("", text)


def create_response(transaction_id: str | None = "txn-created") -> dict[str, Any]:
    transaction = {"id": transaction_id} if transaction_id is not None else None
    return {"createTransaction": {"errors": None, "transaction": transaction}}


def detail(
    *,
    txn: str = "txn-created",
    date: str = "2026-01-15",
    amount: float | None = 12.34,
    account: str | None = "ACC1",
    category: str | None = "CAT1",
    merchant: str | None = "Coffee Shop",
    notes: str | None = None,
) -> dict[str, Any]:
    return {
        "getTransaction": {
            "id": txn,
            "date": date,
            "amount": amount,
            "account": {"id": account},
            "category": {"id": category},
            "merchant": {"id": "mer-1", "name": merchant},
            "notes": notes,
        }
    }


@pytest.fixture(autouse=True)
def policy() -> None:
    set_mutation_authorized(True)
    set_config(Config(confirm_destructive=False))
    yield
    reset_mutation_authorization()
    reset_config()


def client() -> MagicMock:
    mock = MagicMock()
    mock.get_transaction_details = AsyncMock()
    mock.create_transaction = AsyncMock()
    mock.delete_transaction = AsyncMock()
    return mock


def invoke(mock: MagicMock, args: list[str]):
    with patch("monarch_cli.commands.transactions.get_authenticated_client", return_value=mock):
        return runner.invoke(app, args)


def envelope_keys(output: dict[str, Any]) -> set[str]:
    return set(output.keys())


# --- discovery and help ------------------------------------------------------


def test_commands_are_registered_with_explicit_effects() -> None:
    inventory = collect_command_effects(root_app)
    assert inventory["transactions create"] == frozenset({Effect.REMOTE_MUTATION})
    assert inventory["transactions delete"] == frozenset({Effect.REMOTE_MUTATION})


def test_help_documents_authorization_and_examples() -> None:
    env = {"COLUMNS": "200", "NO_COLOR": "1", "TERM": "dumb"}
    for path in (["transactions", "create"], ["transactions", "delete"]):
        result = runner.invoke(root_app, [*path, "--help"], env=env)
        out = _plain(result.stdout + (result.stderr or ""))
        assert result.exit_code == 0, (path, out)
        assert "--allow-mutations" in out
        assert "before the command path" in out
        assert "--dry-run" in out
        assert "Examples:" in out


# --- local validation before any client/API work ----------------------------


@pytest.mark.parametrize(
    "args",
    [
        [*CREATE_BASE[:2], "not-a-date", *CREATE_BASE[3:]],
        ["create", *CREATE_BASE[1:], "--account-id", "   "],
        ["create", *CREATE_BASE[1:], "--category-id", "   "],
        ["create", *CREATE_BASE[1:], "--merchant", "  "],
    ],
)
def test_create_validation_rejects_bad_input_before_client(args: list[str]) -> None:
    with patch(
        "monarch_cli.commands.transactions.get_authenticated_client",
        side_effect=AssertionError("client must not be created for invalid input"),
    ):
        result = runner.invoke(app, args)
    assert result.exit_code == 2, result.output
    assert json.loads(_plain(result.stderr))["code"] == "INVALID_INPUT"


def test_create_rejects_non_finite_amount_before_client() -> None:
    with patch(
        "monarch_cli.commands.transactions.get_authenticated_client",
        side_effect=AssertionError("client must not be created for invalid input"),
    ):
        result = runner.invoke(app, [*CREATE_BASE, "--amount", "nan"])
    assert result.exit_code == 2, result.output


def test_create_requires_all_required_options() -> None:
    result = runner.invoke(app, ["create", "--date", "2026-01-15"])
    assert result.exit_code != 0


def test_create_rejects_positional_target() -> None:
    mock = client()
    result = invoke(mock, [*CREATE_BASE, "EXTRA_POSITIONAL"])
    assert result.exit_code != 0
    assert "positional" in _plain(result.output + (result.stderr or "")).lower()
    mock.create_transaction.assert_not_awaited()


def test_delete_requires_transaction_id_option() -> None:
    result = runner.invoke(app, ["delete"])
    assert result.exit_code != 0


def test_delete_rejects_positional_target() -> None:
    mock = client()
    result = invoke(mock, ["delete", "txn-1", "--transaction-id", "txn-1"])
    assert result.exit_code != 0
    assert "positional" in _plain(result.output + (result.stderr or "")).lower()
    mock.delete_transaction.assert_not_awaited()


def test_delete_empty_transaction_id_is_usage_error() -> None:
    with patch(
        "monarch_cli.commands.transactions.get_authenticated_client",
        side_effect=AssertionError("client must not be created for invalid input"),
    ):
        result = runner.invoke(app, ["delete", "--transaction-id", "  "])
    assert result.exit_code == 2


# --- dry-run is local-only ---------------------------------------------------


def test_create_dry_run_validates_without_client() -> None:
    set_mutation_authorized(False)
    with patch(
        "monarch_cli.commands.transactions.get_authenticated_client",
        side_effect=AssertionError("dry-run must not create a client"),
    ):
        result = runner.invoke(app, [*CREATE_BASE, "--dry-run"])
    assert result.exit_code == 0, result.output
    output = json.loads(result.stdout)
    assert output["status"] == "dry_run"
    assert output["operation"] == "transactions.create"
    assert output["target"] == {"account_id": "ACC1", "date": "2026-01-15"}
    assert output["detail"]["merchant"] == "Coffee Shop"
    assert output["detail"]["amount"] == 12.34


def test_delete_dry_run_validates_without_client_or_read() -> None:
    set_mutation_authorized(False)
    with patch(
        "monarch_cli.commands.transactions.get_authenticated_client",
        side_effect=AssertionError("dry-run must not create a client"),
    ):
        result = runner.invoke(app, [*DELETE_BASE, "--dry-run"])
    assert result.exit_code == 0, result.output
    output = json.loads(result.stdout)
    assert output["status"] == "dry_run"
    assert output["operation"] == "transactions.delete"
    assert output["target"] == {"transaction_id": "txn-1"}


# --- authorization -----------------------------------------------------------


def test_create_blocked_before_client_lookup() -> None:
    set_mutation_authorized(False)
    with patch(
        "monarch_cli.commands.transactions.get_authenticated_client",
        side_effect=AssertionError("client lookup must be gated"),
    ):
        result = runner.invoke(app, CREATE_BASE)
    assert result.exit_code == 3
    assert json.loads(_plain(result.stderr))["code"] == "MUTATION_BLOCKED"


def test_delete_blocked_before_client_lookup() -> None:
    set_mutation_authorized(False)
    with patch(
        "monarch_cli.commands.transactions.get_authenticated_client",
        side_effect=AssertionError("client lookup must be gated"),
    ):
        result = runner.invoke(app, DELETE_BASE)
    assert result.exit_code == 3
    assert json.loads(_plain(result.stderr))["code"] == "MUTATION_BLOCKED"


def test_delete_yes_does_not_authorize() -> None:
    set_mutation_authorized(False)
    with patch(
        "monarch_cli.commands.transactions.get_authenticated_client",
        side_effect=AssertionError("client lookup must be gated"),
    ):
        result = runner.invoke(
            root_app, ["--yes", "transactions", "delete", "--transaction-id", "txn-1"]
        )
    assert result.exit_code == 3


# --- create exact API mapping and success ------------------------------------


def test_create_maps_exact_arguments_and_verifies() -> None:
    mock = client()
    mock.create_transaction.return_value = create_response()
    mock.get_transaction_details.return_value = detail()
    result = invoke(mock, CREATE_BASE)
    assert result.exit_code == 0, result.output
    kwargs = mock.create_transaction.await_args.kwargs
    assert kwargs == {
        "date": "2026-01-15",
        "account_id": "ACC1",
        "amount": 12.34,
        "merchant_name": "Coffee Shop",
        "category_id": "CAT1",
        "notes": "",
    }
    # Bounded exact-ID readback, no pending redirect.
    read_kwargs = mock.get_transaction_details.await_args.kwargs
    assert read_kwargs == {"transaction_id": "txn-created", "redirect_posted": False}
    output = json.loads(result.stdout)
    assert output["operation"] == "transactions.create"
    assert output["status"] == "succeeded"
    assert envelope_keys(output) == {
        "schema_version",
        "operation",
        "status",
        "summary",
        "items",
        "verification",
    }
    assert output["items"][0]["id"] == "txn-created"
    assert output["items"][0]["result"]["merchant"] == "Coffee Shop"
    assert output["items"][0]["result"]["account_id"] == "ACC1"


def test_create_passes_notes_when_provided() -> None:
    mock = client()
    mock.create_transaction.return_value = create_response()
    mock.get_transaction_details.return_value = detail(notes="Team lunch")
    result = invoke(mock, [*CREATE_BASE, "--notes", "Team lunch"])
    assert result.exit_code == 0, result.output
    assert mock.create_transaction.await_args.kwargs["notes"] == "Team lunch"
    assert json.loads(result.stdout)["items"][0]["result"]["notes"] == "Team lunch"


def test_create_does_not_retry() -> None:
    mock = client()
    mock.create_transaction.return_value = create_response()
    mock.get_transaction_details.return_value = detail()
    invoke(mock, CREATE_BASE)
    mock.create_transaction.assert_awaited_once()


# --- create failure classification -------------------------------------------


def test_create_payload_errors_are_definitive_failure() -> None:
    mock = client()
    mock.create_transaction.return_value = {
        "createTransaction": {"errors": [{"code": "BAD", "message": "rejected"}]}
    }
    result = invoke(mock, CREATE_BASE)
    assert result.exit_code == 1
    output = json.loads(result.stdout)
    assert output["status"] == "failed"
    assert output["items"][0]["error"]["details"]["payload_errors"][0]["code"] == "BAD"
    assert mock.get_transaction_details.await_count == 0


def test_create_missing_identity_is_ambiguous() -> None:
    mock = client()
    mock.create_transaction.return_value = create_response(transaction_id=None)
    result = invoke(mock, CREATE_BASE)
    assert result.exit_code == 4
    output = json.loads(result.stdout)
    assert output["status"] == "ambiguous"
    assert output["items"][0]["error"]["details"]["reason"] == "missing_identity"
    assert output["verification"]["required"] is True
    assert mock.get_transaction_details.await_count == 0


@pytest.mark.parametrize(
    "payload",
    [
        "not-a-mapping",
        {"createTransaction": None},
    ],
)
def test_create_malformed_response_is_ambiguous(payload: object) -> None:
    mock = client()
    mock.create_transaction.return_value = payload
    result = invoke(mock, CREATE_BASE)
    assert result.exit_code == 4
    assert json.loads(result.stdout)["items"][0]["error"]["details"]["reason"] == (
        "malformed_response"
    )


def test_create_transport_ambiguity_is_not_retried() -> None:
    from monarch_cli.core.exceptions import MutationAmbiguousError

    mock = client()
    mock.create_transaction.side_effect = MutationAmbiguousError(
        "timeout after dispatch",
        details={"reason": "timeout", "remote_state": "unknown"},
    )
    result = invoke(mock, CREATE_BASE)
    assert result.exit_code == 4
    mock.create_transaction.assert_awaited_once()
    output = json.loads(result.stdout)
    assert output["status"] == "ambiguous"
    assert output["items"][0]["error"]["details"]["reason"] == "timeout"
    assert output["verification"]["command"] == ["monarch", "transactions", "list"]


def test_create_cancellation_is_ambiguous() -> None:
    import asyncio

    mock = client()
    mock.create_transaction.side_effect = asyncio.CancelledError()
    result = invoke(mock, CREATE_BASE)
    assert result.exit_code == 4
    mock.create_transaction.assert_awaited_once()
    details = json.loads(result.stdout)["items"][0]["error"]["details"]
    assert details["reason"] == "cancelled"
    assert details["remote_state"] == "unknown"


def test_create_definitive_failure_is_sanitized() -> None:
    from monarch_cli.core.exceptions import APIError

    mock = client()
    mock.create_transaction.side_effect = APIError("Forbidden", status_code=403)
    result = invoke(mock, CREATE_BASE)
    assert result.exit_code == 1
    output = json.loads(result.stdout)
    assert output["status"] == "failed"
    assert output["items"][0]["error"]["code"] == "API_ERROR"
    assert output["items"][0]["error"]["details"]["status_code"] == 403
    assert output["schema_version"] == "mutation-outcome.v1"


def test_create_readback_failure_is_ambiguous() -> None:
    mock = client()
    mock.create_transaction.return_value = create_response()
    mock.get_transaction_details.side_effect = [RuntimeError("secret upstream text")]
    result = invoke(mock, CREATE_BASE)
    assert result.exit_code == 4
    output = json.loads(result.stdout)
    assert output["items"][0]["error"]["details"]["reason"] == "verification_unavailable"
    assert "secret upstream text" not in result.stdout


def test_create_readback_not_found_is_ambiguous() -> None:
    mock = client()
    mock.create_transaction.return_value = create_response()
    mock.get_transaction_details.return_value = {"getTransaction": None}
    result = invoke(mock, CREATE_BASE)
    assert result.exit_code == 4
    output = json.loads(result.stdout)
    assert output["items"][0]["error"]["details"]["reason"] == "verification_mismatch"
    assert output["items"][0]["error"]["details"]["observed_transaction_id"] is None


def test_create_readback_identity_mismatch_is_ambiguous() -> None:
    mock = client()
    mock.create_transaction.return_value = create_response()
    mock.get_transaction_details.return_value = detail(txn="other-txn")
    result = invoke(mock, CREATE_BASE)
    assert result.exit_code == 4
    details = json.loads(result.stdout)["items"][0]["error"]["details"]
    assert details["reason"] == "verification_mismatch"
    assert details["observed_transaction_id"] == "other-txn"


@pytest.mark.parametrize(
    "observed,field",
    [
        (detail(date="2026-02-01"), "date"),
        (detail(amount=99.99), "amount"),
        (detail(account="OTHER"), "account_id"),
        (detail(category="OTHER"), "category_id"),
        (detail(merchant="Other Store"), "merchant"),
        (detail(notes="unexpected"), "notes"),
    ],
)
def test_create_verification_mismatch_is_ambiguous(observed: dict[str, Any], field: str) -> None:
    mock = client()
    mock.create_transaction.return_value = create_response()
    mock.get_transaction_details.return_value = observed
    result = invoke(mock, CREATE_BASE)
    assert result.exit_code == 4
    details = json.loads(result.stdout)["items"][0]["error"]["details"]
    assert details["reason"] == "verification_mismatch"
    assert field in details["mismatched_fields"]


# --- delete pre-read and confirmation ----------------------------------------


def test_delete_missing_target_is_not_found_without_delete() -> None:
    mock = client()
    mock.get_transaction_details.return_value = {"getTransaction": None}
    result = invoke(mock, DELETE_BASE)
    assert result.exit_code == 1
    assert json.loads(_plain(result.stderr))["code"] == "NOT_FOUND"
    mock.delete_transaction.assert_not_awaited()


def test_delete_pre_read_failure_is_structured_error() -> None:
    from monarch_cli.core.exceptions import APIError

    mock = client()
    mock.get_transaction_details.side_effect = APIError("boom", status_code=500)
    result = invoke(mock, DELETE_BASE)
    assert result.exit_code == 1
    assert json.loads(_plain(result.stderr))["code"] == "API_ERROR"
    assert result.stdout.strip() == ""
    mock.delete_transaction.assert_not_awaited()


def test_delete_identity_mismatch_refuses_before_delete() -> None:
    mock = client()
    mock.get_transaction_details.return_value = detail(txn="other")
    result = invoke(mock, DELETE_BASE)
    assert result.exit_code == 1
    assert "identity" in _plain(result.stderr).lower()
    mock.delete_transaction.assert_not_awaited()


def test_delete_requires_confirmation_when_enabled() -> None:
    set_config(Config(confirm_destructive=True))
    mock = client()
    mock.get_transaction_details.return_value = detail(txn="txn-1")
    with patch(
        "monarch_cli.commands.mutation_helpers.confirm_action", return_value=False
    ) as confirm:
        result = invoke(mock, DELETE_BASE)
    assert result.exit_code == 2
    confirm.assert_called_once()
    mock.delete_transaction.assert_not_awaited()


def test_delete_proceeds_when_confirmed() -> None:
    set_config(Config(confirm_destructive=True))
    mock = client()
    mock.get_transaction_details.side_effect = [detail(txn="txn-1"), {"getTransaction": None}]
    mock.delete_transaction.return_value = True
    with patch("monarch_cli.commands.mutation_helpers.confirm_action", return_value=True):
        result = invoke(mock, DELETE_BASE)
    assert result.exit_code == 0, result.output
    mock.delete_transaction.assert_awaited_once_with("txn-1")


# --- delete success and failure classification -------------------------------


def test_delete_success_verifies_absence() -> None:
    mock = client()
    mock.get_transaction_details.side_effect = [detail(txn="txn-1"), {"getTransaction": None}]
    mock.delete_transaction.return_value = True
    result = invoke(mock, DELETE_BASE)
    assert result.exit_code == 0, result.output
    output = json.loads(result.stdout)
    assert output["operation"] == "transactions.delete"
    assert output["status"] == "succeeded"
    assert output["items"][0]["result"] == {"deleted": True}
    assert envelope_keys(output) == {
        "schema_version",
        "operation",
        "status",
        "summary",
        "items",
        "verification",
    }
    assert mock.get_transaction_details.await_count == 2
    for call in mock.get_transaction_details.await_args_list:
        assert call.kwargs["redirect_posted"] is False


def test_delete_falsy_result_is_definitive_failure() -> None:
    mock = client()
    mock.get_transaction_details.return_value = detail(txn="txn-1")
    mock.delete_transaction.return_value = False
    result = invoke(mock, DELETE_BASE)
    assert result.exit_code == 1
    output = json.loads(result.stdout)
    assert output["status"] == "failed"
    assert output["items"][0]["error"]["code"] == "API_ERROR"


def test_delete_still_present_is_ambiguous() -> None:
    mock = client()
    mock.get_transaction_details.side_effect = [detail(txn="txn-1"), detail(txn="txn-1")]
    mock.delete_transaction.return_value = True
    result = invoke(mock, DELETE_BASE)
    assert result.exit_code == 4
    output = json.loads(result.stdout)
    assert output["status"] == "ambiguous"
    assert output["items"][0]["error"]["details"]["reason"] == "verification_mismatch"


def test_delete_verification_read_failure_is_ambiguous() -> None:
    mock = client()
    mock.get_transaction_details.side_effect = [detail(txn="txn-1"), RuntimeError("boom")]
    mock.delete_transaction.return_value = True
    result = invoke(mock, DELETE_BASE)
    assert result.exit_code == 4
    details = json.loads(result.stdout)["items"][0]["error"]["details"]
    assert details["reason"] == "verification_unavailable"


def test_delete_transport_ambiguity_is_not_retried() -> None:
    from monarch_cli.core.exceptions import MutationAmbiguousError

    mock = client()
    mock.get_transaction_details.return_value = detail(txn="txn-1")
    mock.delete_transaction.side_effect = MutationAmbiguousError(
        "disconnect after dispatch",
        details={"reason": "transport_failure", "remote_state": "unknown"},
    )
    result = invoke(mock, DELETE_BASE)
    assert result.exit_code == 4
    mock.delete_transaction.assert_awaited_once()
    output = json.loads(result.stdout)
    assert output["items"][0]["error"]["details"]["reason"] == "transport_failure"
    assert output["verification"]["command"] == ["monarch", "transactions", "get", "txn-1"]


def test_delete_cancellation_is_ambiguous() -> None:
    import asyncio

    mock = client()
    mock.get_transaction_details.return_value = detail(txn="txn-1")
    mock.delete_transaction.side_effect = asyncio.CancelledError()
    result = invoke(mock, DELETE_BASE)
    assert result.exit_code == 4
    mock.delete_transaction.assert_awaited_once()
    details = json.loads(result.stdout)["items"][0]["error"]["details"]
    assert details["reason"] == "cancelled"
    assert details["remote_state"] == "unknown"


def test_delete_definitive_failure_is_sanitized() -> None:
    from monarch_cli.core.exceptions import APIError

    mock = client()
    mock.get_transaction_details.return_value = detail(txn="txn-1")
    mock.delete_transaction.side_effect = APIError("Forbidden", status_code=403)
    result = invoke(mock, DELETE_BASE)
    assert result.exit_code == 1
    output = json.loads(result.stdout)
    assert output["status"] == "failed"
    assert output["items"][0]["error"]["details"]["status_code"] == 403
    assert output["schema_version"] == "mutation-outcome.v1"
