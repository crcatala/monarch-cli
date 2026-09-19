"""Contract tests for the guarded monthly category budget mutation (mc-9u99)."""

from __future__ import annotations

import json
import re
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from monarch_cli.commands.budgets import app
from monarch_cli.core.config import Config, reset_config, set_config
from monarch_cli.core.operations import reset_mutation_authorization, set_mutation_authorized
from monarch_cli.services.budgets import (
    parse_currency_amount,
    validate_category_id,
    validate_month_start,
)

runner = CliRunner()

_ANSI = re.compile(r"\x1b\[[0-9;]*m")

CATEGORY = "cat-123"
MONTH = "2026-09-01"
BASE = ["set", "--category-id", CATEGORY, "--amount", "500.00", "--start", MONTH]


def _plain(text: str) -> str:
    return _ANSI.sub("", text)


def categories_response(*, ids: list[str] | None = None) -> dict[str, Any]:
    return {"categories": [{"id": cid, "__typename": "Category"} for cid in (ids or [CATEGORY])]}


def budgets_response(
    *,
    category_id: str = CATEGORY,
    month: str = MONTH,
    planned: Any = 500.0,
    include_month: bool = True,
) -> dict[str, Any]:
    amounts = []
    if include_month:
        amounts.append(
            {
                "month": month,
                "plannedCashFlowAmount": planned,
                "actualAmount": 0,
                "remainingAmount": planned,
            }
        )
    return {
        "budgetData": {
            "monthlyAmountsByCategory": [
                {"category": {"id": category_id}, "monthlyAmounts": amounts}
            ]
        }
    }


def mutation_ok() -> dict[str, Any]:
    return {"updateOrCreateBudgetItem": {"budgetItem": {"id": "bi-1", "budgetAmount": 500.0}}}


@pytest.fixture(autouse=True)
def policy() -> None:
    set_mutation_authorized(True)
    set_config(Config(confirm_destructive=False))
    yield
    reset_mutation_authorization()
    reset_config()


def client() -> MagicMock:
    mock = MagicMock()
    mock.get_transaction_categories = AsyncMock(return_value=categories_response())
    mock.get_budgets = AsyncMock(return_value=budgets_response())
    mock.set_budget_amount = AsyncMock(return_value=mutation_ok())
    return mock


def invoke(mock: MagicMock, args: list[str]):
    with patch("monarch_cli.commands.budgets.get_authenticated_client", return_value=mock):
        return runner.invoke(app, args)


# --- amount parsing unit contract -------------------------------------------


class TestParseCurrencyAmount:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("0", Decimal("0.00")),
            ("0.00", Decimal("0.00")),
            ("500", Decimal("500.00")),
            ("500.5", Decimal("500.50")),
            ("12.34", Decimal("12.34")),
        ],
    )
    def test_accepts_valid_amounts(self, raw: str, expected: Decimal) -> None:
        assert parse_currency_amount(raw) == expected

    @pytest.mark.parametrize("raw", ["nan", "inf", "-inf", "Infinity"])
    def test_rejects_non_finite(self, raw: str) -> None:
        from monarch_cli.core.exceptions import ValidationError

        with pytest.raises(ValidationError):
            parse_currency_amount(raw)

    @pytest.mark.parametrize("raw", ["-1", "-0.01", "abc", "", "  ", "1.234", "1e-3"])
    def test_rejects_invalid(self, raw: str) -> None:
        from monarch_cli.core.exceptions import ValidationError

        with pytest.raises(ValidationError):
            parse_currency_amount(raw)

    def test_rejects_amount_not_exactly_representable_on_the_wire(self) -> None:
        from monarch_cli.core.exceptions import ValidationError

        with pytest.raises(ValidationError):
            parse_currency_amount("9999999999999999.99")

    def test_zero_is_valid_reset_amount(self) -> None:
        assert parse_currency_amount("0.00") == Decimal("0.00")


class TestLocalValidators:
    def test_empty_category_id_rejected(self) -> None:
        from monarch_cli.core.exceptions import ValidationError

        with pytest.raises(ValidationError):
            validate_category_id("   ")

    def test_non_first_of_month_rejected(self) -> None:
        from datetime import date

        from monarch_cli.core.exceptions import ValidationError

        with pytest.raises(ValidationError):
            validate_month_start(date(2026, 9, 2))

    def test_first_of_month_accepted(self) -> None:
        from datetime import date

        validate_month_start(date(2026, 9, 1))


# --- local validation precedes every call -----------------------------------


@pytest.mark.parametrize(
    "args",
    [
        ["set", "--category-id", "  ", "--amount", "1.00", "--start", MONTH],
        ["set", "--category-id", CATEGORY, "--amount", "1.00", "--start", "2026-09-02"],
        ["set", "--category-id", CATEGORY, "--amount", "1.00", "--start", "09/01/2026"],
        ["set", "--category-id", CATEGORY, "--amount", "nan", "--start", MONTH],
        ["set", "--category-id", CATEGORY, "--amount", "1.234", "--start", MONTH],
        ["set", "--category-id", CATEGORY, "--amount=-1.00", "--start", MONTH],
    ],
)
def test_local_validation_rejects_before_any_call(args: list[str]) -> None:
    with patch(
        "monarch_cli.commands.budgets.get_authenticated_client",
        side_effect=AssertionError("client must not be created for invalid input"),
    ):
        result = runner.invoke(app, args)
    assert result.exit_code == 2, result.output
    assert _plain(result.stderr).strip()


def test_removed_positional_target_is_rejected() -> None:
    mock = client()
    result = invoke(mock, [*BASE, "cat-123"])
    assert result.exit_code != 0
    assert "positional" in _plain(result.output).lower()
    mock.set_budget_amount.assert_not_awaited()


@pytest.mark.parametrize("option", ["--group", "--future", "--flex", "--reset", "--rollover"])
def test_unsupported_scope_options_are_rejected(option: str) -> None:
    mock = client()
    result = invoke(mock, [*BASE, option, "x"])
    assert result.exit_code != 0
    mock.set_budget_amount.assert_not_awaited()


# --- authorization -----------------------------------------------------------


def test_blocked_before_client_lookup() -> None:
    set_mutation_authorized(False)
    with patch(
        "monarch_cli.commands.budgets.get_authenticated_client",
        side_effect=AssertionError("client lookup must be gated"),
    ):
        result = runner.invoke(app, BASE)
    assert result.exit_code == 3
    assert json.loads(result.stderr)["code"] == "MUTATION_BLOCKED"


# --- discovery ---------------------------------------------------------------


def test_unknown_category_fails_closed_without_write() -> None:
    mock = client()
    mock.get_transaction_categories.return_value = categories_response(ids=["other"])
    result = invoke(mock, BASE)
    assert result.exit_code == 1
    assert "category" in _plain(result.stderr).lower()
    mock.set_budget_amount.assert_not_awaited()
    mock.get_budgets.assert_not_awaited()


def test_malformed_discovery_fails_closed() -> None:
    mock = client()
    mock.get_transaction_categories.return_value = {"categories": "nope"}
    result = invoke(mock, BASE)
    assert result.exit_code == 1
    mock.set_budget_amount.assert_not_awaited()


# --- exact argument mapping and success -------------------------------------


def test_success_sends_exact_intended_arguments_and_reads_back() -> None:
    mock = client()
    result = invoke(mock, BASE)
    assert result.exit_code == 0, result.output
    mock.set_budget_amount.assert_awaited_once_with(
        category_id=CATEGORY,
        amount=500.0,
        timeframe="month",
        start_date=MONTH,
        apply_to_future=False,
    )
    mock.get_budgets.assert_awaited_once_with(start_date=MONTH, end_date=MONTH)
    output = json.loads(result.stdout)
    assert output["schema_version"] == "mutation-outcome.v1"
    assert output["operation"] == "budgets.set"
    assert output["status"] == "succeeded"
    assert output["items"][0]["entity"] == "budget"
    assert output["items"][0]["id"] == CATEGORY
    result_obj = output["items"][0]["result"]
    assert result_obj["category_id"] == CATEGORY
    assert result_obj["month"] == MONTH
    assert result_obj["requested_amount"] == "500.00"
    assert result_obj["observed_amount"] == "500.00"
    # No raw upstream payload leaks.
    assert "budgetData" not in result.stdout
    assert "updateOrCreateBudgetItem" not in result.stdout


def test_zero_amount_is_valid_reset() -> None:
    mock = client()
    mock.get_budgets.return_value = budgets_response(planned=0)
    result = invoke(mock, ["set", "--category-id", CATEGORY, "--amount", "0", "--start", MONTH])
    assert result.exit_code == 0, result.output
    args = mock.set_budget_amount.await_args.kwargs
    assert args["amount"] == 0.0
    output = json.loads(result.stdout)
    assert output["items"][0]["result"]["observed_amount"] == "0.00"


def test_success_uses_cent_normalized_comparison() -> None:
    mock = client()
    mock.get_budgets.return_value = budgets_response(planned=500)
    result = invoke(mock, BASE)
    assert result.exit_code == 0, result.output


# --- dry-run isolation -------------------------------------------------------


def test_dry_run_validates_and_discovers_but_does_not_write() -> None:
    set_mutation_authorized(False)
    mock = client()
    result = invoke(mock, [*BASE, "--dry-run"])
    assert result.exit_code == 0, result.output
    output = json.loads(result.stdout)
    assert output["status"] == "dry_run"
    assert output["operation"] == "budgets.set"
    assert output["target"] == {"category_id": CATEGORY, "start": MONTH}
    assert output["detail"]["timeframe"] == "month"
    assert output["detail"]["apply_to_future"] is False
    mock.set_budget_amount.assert_not_awaited()
    mock.get_budgets.assert_not_awaited()
    mock.get_transaction_categories.assert_awaited_once()


def test_dry_run_still_fails_closed_on_unknown_category() -> None:
    mock = client()
    mock.get_transaction_categories.return_value = categories_response(ids=["other"])
    result = invoke(mock, [*BASE, "--dry-run"])
    assert result.exit_code == 1
    mock.set_budget_amount.assert_not_awaited()


# --- failure / ambiguity classification -------------------------------------


def test_definitive_rejection_is_failed_and_not_retried() -> None:
    from monarch_cli.core.exceptions import APIError

    mock = client()
    mock.set_budget_amount.side_effect = APIError("Forbidden", status_code=403)
    result = invoke(mock, BASE)
    assert result.exit_code == 1
    output = json.loads(result.stdout)
    assert output["status"] == "failed"
    assert output["verification"] is None
    assert output["items"][0]["error"]["code"] == "API_ERROR"
    mock.set_budget_amount.assert_awaited_once()
    mock.get_budgets.assert_not_awaited()


def test_graphql_payload_errors_are_definitive_failure() -> None:
    mock = client()
    mock.set_budget_amount.return_value = {
        "errors": [{"message": "bad"}],
        "updateOrCreateBudgetItem": {"budgetItem": {"id": "bi"}},
    }
    result = invoke(mock, BASE)
    assert result.exit_code == 1
    assert json.loads(result.stdout)["status"] == "failed"
    mock.get_budgets.assert_not_awaited()


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"updateOrCreateBudgetItem": {"budgetItem": None}},
        {"updateOrCreateBudgetItem": "nope"},
    ],
)
def test_malformed_write_response_is_ambiguous(payload: dict[str, Any]) -> None:
    mock = client()
    mock.set_budget_amount.return_value = payload
    result = invoke(mock, BASE)
    assert result.exit_code == 4
    output = json.loads(result.stdout)
    assert output["status"] == "ambiguous"
    assert output["verification"]["required"] is True
    mock.get_budgets.assert_not_awaited()


def test_gql_transport_failure_is_ambiguous_with_verification() -> None:
    """The real gql-wrapped transport failure reaches the ambiguous contract (mc-ic7w).

    The client method raises the production exception type
    (``TransportConnectionFailed``), not an aiohttp/stdlib type, so the
    command's mutation boundary must still classify it as ambiguous.
    """
    from gql.transport.exceptions import TransportConnectionFailed

    mock = client()
    mock.set_budget_amount.side_effect = TransportConnectionFailed("simulated disconnect")
    result = invoke(mock, BASE)
    assert result.exit_code == 4
    output = json.loads(result.stdout)
    assert output["status"] == "ambiguous"
    assert output["verification"]["required"] is True
    details = output["items"][0]["error"]["details"]
    assert details["remote_state"] == "unknown"
    assert details["reason"] == "transport_failure"
    assert output["items"][0]["error"]["code"] == "MUTATION_AMBIGUOUS"
    mock.set_budget_amount.assert_awaited_once()
    mock.get_budgets.assert_not_awaited()


def test_transport_ambiguity_is_not_retried() -> None:
    from monarch_cli.core.exceptions import MutationAmbiguousError

    mock = client()
    mock.set_budget_amount.side_effect = MutationAmbiguousError(
        "timeout after dispatch",
        details={"reason": "timeout", "remote_state": "unknown"},
    )
    result = invoke(mock, BASE)
    assert result.exit_code == 4
    mock.set_budget_amount.assert_awaited_once()
    output = json.loads(result.stdout)
    assert output["status"] == "ambiguous"
    assert output["items"][0]["error"]["details"]["remote_state"] == "unknown"


def test_readback_mismatch_is_ambiguous() -> None:
    mock = client()
    mock.get_budgets.return_value = budgets_response(planned=123.0)
    result = invoke(mock, BASE)
    assert result.exit_code == 4
    output = json.loads(result.stdout)
    assert output["status"] == "ambiguous"
    details = output["items"][0]["error"]["details"]
    assert details["reason"] == "verification_mismatch"
    assert details["observed_amount"] == "123.00"


def test_readback_unavailable_is_ambiguous() -> None:
    mock = client()
    mock.get_budgets.return_value = budgets_response(include_month=False)
    result = invoke(mock, BASE)
    assert result.exit_code == 4
    details = json.loads(result.stdout)["items"][0]["error"]["details"]
    assert details["reason"] == "verification_unavailable"
    assert details["remote_state"] == "unknown"


def test_readback_call_failure_is_ambiguous_not_failed() -> None:
    mock = client()
    mock.get_budgets.side_effect = RuntimeError("boom")
    result = invoke(mock, BASE)
    assert result.exit_code == 4
    output = json.loads(result.stdout)
    assert output["status"] == "ambiguous"
    assert output["items"][0]["error"]["details"]["reason"] == "verification_unavailable"


# --- discovery --------------------------------------------------------------


def test_help_documents_scope_and_authorization() -> None:
    result = runner.invoke(app, ["set", "--help"], env={"COLUMNS": "200", "NO_COLOR": "1"})
    assert result.exit_code == 0
    out = _plain(result.stdout)
    assert "--allow-mutations" in out
    assert "before the command path" in out
    assert "--dry-run" in out
    assert "--category-id" in out
    assert "--group" not in out
    assert "--future" not in out
