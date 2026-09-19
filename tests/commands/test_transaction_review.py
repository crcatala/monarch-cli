"""Contract tests for explicit transaction review-state mutations (mc-e49c)."""

from __future__ import annotations

import json
import re
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from monarch_cli.commands.transaction_review import app
from monarch_cli.core.config import Config, reset_config, set_config
from monarch_cli.core.operations import reset_mutation_authorization, set_mutation_authorized

runner = CliRunner()

_ANSI = re.compile(r"\x1b\[[0-9;]*m")

MARK = ["mark"]
RETURN = ["return"]


def _plain(text: str) -> str:
    return _ANSI.sub("", text)


def detail(
    *,
    needs_review: bool | None,
    txn: str = "txn-1",
    category: str | None = "cat-1",
    merchant_id: str | None = "mer-1",
    merchant_name: str | None = "Store",
    reviewed_at: str | None = None,
    reviewed_by: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "getTransaction": {
            "id": txn,
            "needsReview": needs_review,
            "reviewedAt": reviewed_at,
            "reviewedByUser": reviewed_by,
            "category": {"id": category},
            "merchant": {"id": merchant_id, "name": merchant_name},
        }
    }


def mutation_ok() -> dict[str, Any]:
    return {"updateTransaction": {"errors": None, "transaction": {"id": "txn-1"}}}


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
    mock.gql_call = AsyncMock()
    return mock


def invoke(mock: MagicMock, args: list[str]):
    with patch(
        "monarch_cli.commands.transaction_review.get_authenticated_client", return_value=mock
    ):
        return runner.invoke(app, args)


# --- exact intent mapping ---------------------------------------------------


def test_mark_sends_only_reviewed_true() -> None:
    mock = client()
    mock.get_transaction_details.side_effect = [
        detail(needs_review=True),
        detail(needs_review=False, reviewed_at="2026-01-01T00:00:00Z"),
    ]
    mock.gql_call.return_value = mutation_ok()
    result = invoke(mock, [*MARK, "--transaction-id", "txn-1"])
    assert result.exit_code == 0, result.output
    variables = mock.gql_call.await_args.kwargs["variables"]
    assert variables == {"input": {"id": "txn-1", "reviewed": True}}
    output = json.loads(result.stdout)
    assert output["operation"] == "transactions.review.mark"
    assert output["items"][0]["result"]["intent"] == "mark_reviewed"
    assert output["items"][0]["result"]["no_op"] is False
    assert output["items"][0]["result"]["needs_review"] is False


def test_return_sends_only_needs_review_true() -> None:
    mock = client()
    mock.get_transaction_details.side_effect = [
        detail(needs_review=False),
        detail(needs_review=True),
    ]
    mock.gql_call.return_value = mutation_ok()
    result = invoke(mock, [*RETURN, "--transaction-id", "txn-1"])
    assert result.exit_code == 0, result.output
    variables = mock.gql_call.await_args.kwargs["variables"]
    assert variables == {"input": {"id": "txn-1", "needsReview": True}}
    output = json.loads(result.stdout)
    assert output["operation"] == "transactions.review.return"
    assert output["items"][0]["result"]["intent"] == "return_to_queue"


@pytest.mark.parametrize(
    "command,needs_review,expected_field",
    [
        (MARK, True, "reviewed"),
        (RETURN, False, "needsReview"),
    ],
)
def test_full_variables_contain_only_identity_and_one_field(
    command: list[str], needs_review: bool, expected_field: str
) -> None:
    mock = client()
    mock.get_transaction_details.side_effect = [
        detail(needs_review=needs_review),
        detail(needs_review=not needs_review),
    ]
    mock.gql_call.return_value = mutation_ok()
    result = invoke(mock, [*command, "--transaction-id", "txn-1"])
    assert result.exit_code == 0, result.output
    serialized = mock.gql_call.await_args.kwargs["variables"]["input"]
    assert serialized == {"id": "txn-1", expected_field: True}
    for unrelated in ("category", "name", "amount", "date", "notes", "goalId"):
        assert unrelated not in serialized


def test_review_output_never_invents_reviewed_boolean() -> None:
    mock = client()
    mock.get_transaction_details.side_effect = [
        detail(needs_review=True),
        detail(needs_review=False, reviewed_by={"id": "u1", "name": "Ada"}),
    ]
    mock.gql_call.return_value = mutation_ok()
    result = invoke(mock, [*MARK, "--transaction-id", "txn-1"])
    output = json.loads(result.stdout)
    result_obj = output["items"][0]["result"]
    assert "reviewed" not in result_obj
    assert result_obj["reviewed_at"] is None
    assert result_obj["reviewed_by_user"] == {"id": "u1", "name": "Ada"}


def test_contradictory_and_false_boolean_options_are_not_accepted() -> None:
    mock = client()
    for option in ("--reviewed", "--needs-review", "--no-reviewed", "--no-needs-review"):
        result = invoke(mock, [*MARK, "--transaction-id", "txn-1", option])
        assert result.exit_code != 0, option
    mock.gql_call.assert_not_awaited()
    mock.get_transaction_details.assert_not_awaited()


# --- pre-read identity and no-op -------------------------------------------


def test_mark_is_noop_when_already_reviewed() -> None:
    mock = client()
    mock.get_transaction_details.return_value = detail(needs_review=False)
    result = invoke(mock, [*MARK, "--transaction-id", "txn-1"])
    assert result.exit_code == 0, result.output
    output = json.loads(result.stdout)
    assert output["status"] == "succeeded"
    assert output["items"][0]["result"]["no_op"] is True
    mock.gql_call.assert_not_awaited()
    assert mock.get_transaction_details.await_count == 1


def test_return_is_noop_when_already_in_queue() -> None:
    mock = client()
    mock.get_transaction_details.return_value = detail(needs_review=True)
    result = invoke(mock, [*RETURN, "--transaction-id", "txn-1"])
    assert result.exit_code == 0, result.output
    output = json.loads(result.stdout)
    assert output["items"][0]["result"]["no_op"] is True
    mock.gql_call.assert_not_awaited()


def test_missing_transaction_is_not_found_and_does_not_write() -> None:
    mock = client()
    mock.get_transaction_details.return_value = {"getTransaction": None}
    result = invoke(mock, [*MARK, "--transaction-id", "txn-1"])
    assert result.exit_code == 1
    assert "transaction" in result.stderr.lower()
    mock.gql_call.assert_not_awaited()


def test_identity_mismatch_refuses_before_write() -> None:
    mock = client()
    mock.get_transaction_details.return_value = detail(needs_review=True, txn="other")
    result = invoke(mock, [*MARK, "--transaction-id", "txn-1"])
    assert result.exit_code != 0
    assert "identity" in _plain(result.stderr).lower()
    mock.gql_call.assert_not_awaited()


# --- post-write verification ------------------------------------------------


def test_verification_mismatch_review_state_is_ambiguous() -> None:
    mock = client()
    mock.get_transaction_details.side_effect = [
        detail(needs_review=True),
        detail(needs_review=True),  # still in queue: write did not take
    ]
    mock.gql_call.return_value = mutation_ok()
    result = invoke(mock, [*MARK, "--transaction-id", "txn-1"])
    assert result.exit_code == 4
    output = json.loads(result.stdout)
    assert output["status"] == "ambiguous"
    assert output["verification"]["required"] is True
    assert output["verification"]["command"] == ["monarch", "transactions", "get", "txn-1"]
    details = output["items"][0]["error"]["details"]
    assert details["reason"] == "verification_mismatch"
    assert "needs_review" in details["mismatched_fields"]


@pytest.mark.parametrize(
    "after",
    [
        detail(needs_review=False, category="cat-CHANGED"),
        detail(needs_review=False, merchant_id="mer-CHANGED"),
        detail(needs_review=False, merchant_name="Renamed"),
    ],
)
def test_unrelated_field_change_is_ambiguous(after: dict[str, Any]) -> None:
    mock = client()
    mock.get_transaction_details.side_effect = [detail(needs_review=True), after]
    mock.gql_call.return_value = mutation_ok()
    result = invoke(mock, [*MARK, "--transaction-id", "txn-1"])
    assert result.exit_code == 4
    details = json.loads(result.stdout)["items"][0]["error"]["details"]
    assert details["reason"] == "verification_mismatch"
    assert set(details["mismatched_fields"]) & {"category_id", "merchant_id", "merchant_name"}


def test_verification_unavailable_is_ambiguous() -> None:
    mock = client()
    mock.get_transaction_details.side_effect = [detail(needs_review=True), RuntimeError("boom")]
    mock.gql_call.return_value = mutation_ok()
    result = invoke(mock, [*MARK, "--transaction-id", "txn-1"])
    assert result.exit_code == 4
    details = json.loads(result.stdout)["items"][0]["error"]["details"]
    assert details["reason"] == "verification_unavailable"
    assert details["remote_state"] == "unknown"


# --- authorization, validation, failures ------------------------------------


def test_blocked_before_client_lookup() -> None:
    set_mutation_authorized(False)
    with patch(
        "monarch_cli.commands.transaction_review.get_authenticated_client",
        side_effect=AssertionError("client lookup must be gated"),
    ):
        result = runner.invoke(app, [*MARK, "--transaction-id", "txn-1"])
    assert result.exit_code == 3
    assert json.loads(result.stderr)["code"] == "MUTATION_BLOCKED"


def test_empty_transaction_id_is_usage_error() -> None:
    mock = client()
    result = invoke(mock, [*MARK, "--transaction-id", "  "])
    assert result.exit_code == 2
    mock.get_transaction_details.assert_not_awaited()


def test_removed_positional_id_is_rejected() -> None:
    mock = client()
    result = invoke(mock, [*MARK, "txn-1"])
    assert result.exit_code != 0
    assert "transaction-id" in _plain(result.output).lower()
    mock.gql_call.assert_not_awaited()


def test_payload_errors_are_definitive_failure() -> None:
    mock = client()
    mock.get_transaction_details.return_value = detail(needs_review=True)
    mock.gql_call.return_value = {
        "updateTransaction": {"errors": [{"code": "PENDING", "message": "pending"}]}
    }
    result = invoke(mock, [*MARK, "--transaction-id", "txn-1"])
    assert result.exit_code == 1
    output = json.loads(result.stdout)
    assert output["status"] == "failed"
    assert output["items"][0]["error"]["details"]["payload_errors"][0]["code"] == "PENDING"
    assert mock.get_transaction_details.await_count == 1


def test_graphql_payload_errors_are_definitive_failure() -> None:
    mock = client()
    mock.get_transaction_details.return_value = detail(needs_review=True)
    mock.gql_call.return_value = {
        "errors": [{"message": "graphql failure"}],
        "updateTransaction": {"errors": None},
    }
    result = invoke(mock, [*MARK, "--transaction-id", "txn-1"])
    assert result.exit_code == 1
    assert json.loads(result.stdout)["status"] == "failed"


@pytest.mark.parametrize(
    "mutation_result",
    [
        {"updateTransaction": {"transaction": {"id": "txn-1"}}},
        {"updateTransaction": {"errors": "not-an-array"}},
    ],
)
def test_malformed_mutation_payload_is_ambiguous(mutation_result: dict[str, Any]) -> None:
    mock = client()
    mock.get_transaction_details.return_value = detail(needs_review=True)
    mock.gql_call.return_value = mutation_result
    result = invoke(mock, [*MARK, "--transaction-id", "txn-1"])
    assert result.exit_code == 4
    output = json.loads(result.stdout)
    assert output["status"] == "ambiguous"
    assert output["items"][0]["error"]["details"]["reason"] == "malformed_response"
    # No verify read after an ambiguous response.
    assert mock.get_transaction_details.await_count == 1


def test_transport_ambiguity_is_not_retried() -> None:
    from monarch_cli.core.exceptions import MutationAmbiguousError

    mock = client()
    mock.get_transaction_details.return_value = detail(needs_review=False)
    mock.gql_call.side_effect = MutationAmbiguousError(
        "timeout after dispatch",
        details={"reason": "timeout", "remote_state": "unknown"},
    )
    result = invoke(mock, [*RETURN, "--transaction-id", "txn-1"])
    assert result.exit_code == 4
    mock.gql_call.assert_awaited_once()
    output = json.loads(result.stdout)
    assert output["status"] == "ambiguous"
    assert output["items"][0]["error"]["details"]["remote_state"] == "unknown"


# --- dry-run / preview ------------------------------------------------------


def test_dry_run_previews_without_write_or_authorization() -> None:
    set_mutation_authorized(False)
    mock = client()
    mock.get_transaction_details.return_value = detail(needs_review=True)
    result = invoke(mock, [*MARK, "--transaction-id", "txn-1", "--dry-run"])
    assert result.exit_code == 0, result.output
    output = json.loads(result.stdout)
    assert output["status"] == "dry_run"
    assert output["operation"] == "transactions.review.mark"
    assert output["detail"]["intent"] == "mark_reviewed"
    assert output["detail"]["no_op"] is False
    mock.gql_call.assert_not_awaited()
