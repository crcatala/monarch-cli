"""Contract tests for guarded transaction split workflows."""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from monarch_cli.commands.transaction_splits import app
from monarch_cli.core.config import Config, reset_config, set_config
from monarch_cli.core.operations import reset_mutation_authorization, set_mutation_authorized

runner = CliRunner()


def _plain(text: str) -> str:
    """Strip Rich ANSI styling so option-name assertions are stable."""
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def payload(amount: float = -10.0, rows: list[dict] | None = None) -> dict:
    return {
        "getTransaction": {
            "id": "txn-1",
            "amount": amount,
            "merchant": {"name": "Store"},
            "category": {"id": "cat-parent", "name": "Shopping"},
            "splitTransactions": rows or [],
        }
    }


def mutation_payload(
    rows: list[dict], errors: list | None = None, *, nullable_errors: bool = False
) -> dict:
    return {
        "updateTransactionSplit": {
            "errors": None if nullable_errors else (errors or []),
            "transaction": {"id": "txn-1", "splitTransactions": rows},
        }
    }


def row(merchant: str = "Store", amount: float = -10.0, category: str = "cat-1") -> dict:
    return {
        "id": "split-1",
        "merchant": {"name": merchant},
        "category": {"id": category, "name": "Shopping"},
        "amount": amount,
        "notes": None,
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
    mock.get_transaction_splits = AsyncMock()
    mock.update_transaction_splits = AsyncMock()
    return mock


def invoke(mock: MagicMock, args: list[str]):
    with patch(
        "monarch_cli.commands.transaction_splits.get_authenticated_client", return_value=mock
    ):
        return runner.invoke(app, args)


def test_show_is_read_only_and_normalized() -> None:
    mock = client()
    mock.get_transaction_splits.return_value = payload(rows=[row()])
    result = invoke(mock, ["show", "txn-1", "--json"])
    assert result.exit_code == 0
    output = json.loads(result.stdout)
    assert output["amount"] == -10.0
    assert output["splits"][0]["category_id"] == "cat-1"
    mock.update_transaction_splits.assert_not_awaited()


def test_replace_inline_reads_parent_then_writes_then_verifies() -> None:
    mock = client()
    mock.get_transaction_splits.side_effect = [payload(), payload(rows=[row()])]
    mock.update_transaction_splits.return_value = mutation_payload([row()], nullable_errors=True)
    result = invoke(
        mock,
        [
            "replace",
            "--transaction-id",
            "txn-1",
            "--splits-json",
            '[{"merchantName":"Store","amount":-10.00,"categoryId":"cat-1"}]',
        ],
    )
    assert result.exit_code == 0
    assert json.loads(result.stdout)["operation"] == "transactions.splits.replace"
    mock.update_transaction_splits.assert_awaited_once_with(
        transaction_id="txn-1",
        split_data=[{"merchantName": "Store", "amount": -10.0, "categoryId": "cat-1"}],
    )
    assert mock.get_transaction_splits.await_count == 2


def test_replace_file_source_and_conflict_are_bounded(tmp_path: Path) -> None:
    source = tmp_path / "splits.json"
    source.write_text('[{"merchantName":"Store","amount":-10,"categoryId":"cat-1"}]')
    mock = client()
    mock.get_transaction_splits.side_effect = [payload(), payload(rows=[row()])]
    mock.update_transaction_splits.return_value = mutation_payload([row()])
    result = invoke(mock, ["replace", "--transaction-id", "txn-1", "--splits-file", str(source)])
    assert result.exit_code == 0

    conflict = invoke(
        mock,
        [
            "replace",
            "--transaction-id",
            "txn-1",
            "--splits-json",
            '[{"merchantName":"Store","amount":-10,"categoryId":"cat-1"}]',
            "--splits-file",
            str(source),
        ],
    )
    assert conflict.exit_code == 2
    assert mock.update_transaction_splits.await_count == 1


def test_replace_rejects_unsupported_fields_and_bad_total_before_write() -> None:
    mock = client()
    mock.get_transaction_splits.return_value = payload()
    unsupported = invoke(
        mock,
        [
            "replace",
            "--transaction-id",
            "txn-1",
            "--splits-json",
            '[{"merchantName":"Store","amount":-10,"categoryId":"cat-1","notes":"no"}]',
        ],
    )
    assert unsupported.exit_code == 2
    mock.get_transaction_splits.assert_not_awaited()
    mock.update_transaction_splits.assert_not_awaited()

    bad_total = invoke(
        mock,
        [
            "replace",
            "--transaction-id",
            "txn-1",
            "--splits-json",
            '[{"merchantName":"Store","amount":-9.99,"categoryId":"cat-1"}]',
        ],
    )
    assert bad_total.exit_code == 2
    mock.update_transaction_splits.assert_not_awaited()


def test_replace_rejects_unrepresentable_wire_amount_before_read() -> None:
    mock = client()
    result = invoke(
        mock,
        [
            "replace",
            "--transaction-id",
            "txn-1",
            "--splits-json",
            '[{"merchantName":"Store","amount":90071992547409.91,"categoryId":"cat-1"}]',
        ],
    )
    assert result.exit_code == 2
    mock.get_transaction_splits.assert_not_awaited()
    mock.update_transaction_splits.assert_not_awaited()


@pytest.mark.parametrize(
    "parent_amount,split_amount",
    [(-10.0, 1.0), (10.0, -1.0), (0.0, 1.0)],
)
def test_replace_rejects_invalid_signs_and_zero_parent(
    parent_amount: float, split_amount: float
) -> None:
    mock = client()
    mock.get_transaction_splits.return_value = payload(amount=parent_amount)
    result = invoke(
        mock,
        [
            "replace",
            "--transaction-id",
            "txn-1",
            "--splits-json",
            json.dumps([{"merchantName": "Store", "amount": split_amount, "categoryId": "cat-1"}]),
        ],
    )
    assert result.exit_code == 2
    mock.update_transaction_splits.assert_not_awaited()


@pytest.mark.parametrize(
    "split_json",
    [
        '[{"merchantName":"Store","amount":-10.001,"categoryId":"cat-1"}]',
        '[{"merchantName":"Store","amount":10000000000000000.00,"categoryId":"cat-1"}]',
    ],
)
def test_replace_rejects_scale_and_precision_before_read(split_json: str) -> None:
    mock = client()
    result = invoke(mock, ["replace", "--transaction-id", "txn-1", "--splits-json", split_json])
    assert result.exit_code == 2
    mock.get_transaction_splits.assert_not_awaited()
    mock.update_transaction_splits.assert_not_awaited()


def test_replace_rejects_more_than_maximum_rows_before_read() -> None:
    mock = client()
    splits = [
        {"merchantName": "Store", "amount": -1, "categoryId": f"cat-{index}"}
        for index in range(101)
    ]
    result = invoke(
        mock, ["replace", "--transaction-id", "txn-1", "--splits-json", json.dumps(splits)]
    )
    assert result.exit_code == 2
    mock.get_transaction_splits.assert_not_awaited()
    mock.update_transaction_splits.assert_not_awaited()


def test_clear_sends_empty_list_and_verifies() -> None:
    mock = client()
    mock.get_transaction_splits.return_value = payload()
    mock.update_transaction_splits.return_value = mutation_payload([], nullable_errors=True)
    result = invoke(mock, ["clear", "--transaction-id", "txn-1"])
    assert result.exit_code == 0
    mock.update_transaction_splits.assert_awaited_once_with(transaction_id="txn-1", split_data=[])
    assert mock.get_transaction_splits.await_count == 1


def test_payload_errors_are_definitive_failure() -> None:
    mock = client()
    mock.get_transaction_splits.return_value = payload()
    mock.update_transaction_splits.return_value = mutation_payload(
        [], [{"code": "PENDING", "message": "pending transaction"}]
    )
    result = invoke(mock, ["clear", "--transaction-id", "txn-1"])
    assert result.exit_code == 1
    output = json.loads(result.stdout)
    assert output["status"] == "failed"
    assert output["items"][0]["error"]["details"]["payload_errors"][0]["code"] == "PENDING"


@pytest.mark.parametrize(
    "mutation_result",
    [
        {"updateTransactionSplit": {"transaction": {"id": "txn-1"}}},
        {"updateTransactionSplit": {"errors": [], "transaction": None}},
        {"updateTransactionSplit": {"errors": "not-an-array", "transaction": {}}},
    ],
)
def test_malformed_mutation_payload_is_ambiguous(mutation_result: dict) -> None:
    mock = client()
    mock.get_transaction_splits.return_value = payload()
    mock.update_transaction_splits.return_value = mutation_result
    result = invoke(mock, ["clear", "--transaction-id", "txn-1"])
    assert result.exit_code == 4
    output = json.loads(result.stdout)
    assert output["status"] == "ambiguous"
    assert output["verification"]["required"] is True
    assert output["items"][0]["error"]["details"]["reason"] == "malformed_response"
    mock.get_transaction_splits.assert_not_awaited()


def test_graphql_payload_errors_remain_definitive_failure() -> None:
    mock = client()
    mock.get_transaction_splits.return_value = payload()
    mock.update_transaction_splits.return_value = {
        "errors": [{"message": "graphql failure"}],
        "updateTransactionSplit": {"errors": [], "transaction": {}},
    }
    result = invoke(mock, ["clear", "--transaction-id", "txn-1"])
    assert result.exit_code == 1
    output = json.loads(result.stdout)
    assert output["status"] == "failed"
    mock.get_transaction_splits.assert_not_awaited()


def test_verification_mismatch_is_ambiguous_and_sanitized() -> None:
    mock = client()
    mock.get_transaction_splits.side_effect = [payload(), payload(rows=[row(category="other")])]
    mock.update_transaction_splits.return_value = mutation_payload([row(category="cat-1")])
    result = invoke(
        mock,
        [
            "replace",
            "--transaction-id",
            "txn-1",
            "--splits-json",
            '[{"merchantName":"Store","amount":-10,"categoryId":"cat-1"}]',
        ],
    )
    assert result.exit_code == 4
    output = json.loads(result.stdout)
    assert output["status"] == "ambiguous"
    assert output["verification"]["command"][-1] == "txn-1"
    details = output["items"][0]["error"]["details"]
    assert "expected" not in details
    assert "observed" not in details
    assert details["mismatched_fields"] == ["categoryId"]


def test_mutation_is_blocked_before_client_lookup() -> None:
    set_mutation_authorized(False)
    with patch(
        "monarch_cli.commands.transaction_splits.get_authenticated_client",
        side_effect=AssertionError("client lookup must be gated"),
    ):
        result = runner.invoke(
            app,
            [
                "replace",
                "--transaction-id",
                "txn-1",
                "--splits-json",
                '[{"merchantName":"Store","amount":-10,"categoryId":"cat-1"}]',
            ],
        )
    assert result.exit_code == 3
    assert json.loads(result.stderr)["code"] == "MUTATION_BLOCKED"


def test_replace_rejects_removed_positional_id() -> None:
    """The removed positional transaction ID is a usage error (mc-vv11)."""
    mock = client()
    result = invoke(mock, ["replace", "txn-1", "--splits-json", "[]"])
    assert result.exit_code != 0
    assert "transaction-id" in _plain(result.output)
    mock.update_transaction_splits.assert_not_awaited()


def test_replace_positional_with_option_reports_removal() -> None:
    """A leftover positional alongside --transaction-id is explicitly rejected."""
    mock = client()
    result = invoke(mock, ["replace", "--transaction-id", "txn-1", "txn-2", "--splits-json", "[]"])
    assert result.exit_code == 2
    assert "no longer supported" in result.output.lower()
    mock.update_transaction_splits.assert_not_awaited()


def test_clear_rejects_removed_positional_id() -> None:
    mock = client()
    result = invoke(mock, ["clear", "txn-1"])
    assert result.exit_code != 0
    assert "transaction-id" in _plain(result.output)
    mock.update_transaction_splits.assert_not_awaited()


def test_replace_rejects_removed_source_aliases() -> None:
    """Legacy split source aliases are removed, not retained as shims."""
    mock = client()
    for alias in ("--json-input", "--input-json"):
        result = invoke(mock, ["replace", "--transaction-id", "txn-1", alias, "[]"])
        assert result.exit_code != 0, result.output
    for alias in ("--file", "--input-file"):
        result = invoke(mock, ["replace", "--transaction-id", "txn-1", alias, "splits.json"])
        assert result.exit_code != 0, result.output
    mock.update_transaction_splits.assert_not_awaited()


def test_replace_dry_run_validates_parent_without_write() -> None:
    mock = client()
    mock.get_transaction_splits.return_value = payload()  # amount -10.0
    result = invoke(
        mock,
        [
            "replace",
            "--transaction-id",
            "txn-1",
            "--splits-json",
            '[{"merchantName":"Store","amount":-10.00,"categoryId":"cat-1"}]',
            "--dry-run",
        ],
    )
    assert result.exit_code == 0, result.output
    payload_out = json.loads(result.stdout)
    assert payload_out["status"] == "dry_run"
    assert payload_out["operation"] == "transactions.splits.replace"
    assert payload_out["detail"]["parent_amount"] == "-10.0"
    assert payload_out["detail"]["splits"][0]["amount"] == -10.0
    mock.update_transaction_splits.assert_not_awaited()


def test_clear_dry_run_reads_current_without_write() -> None:
    mock = client()
    mock.get_transaction_splits.return_value = payload(rows=[row()])
    result = invoke(mock, ["clear", "--transaction-id", "txn-1", "--dry-run"])
    assert result.exit_code == 0, result.output
    detail = json.loads(result.stdout)["detail"]
    assert detail["current_split_count"] == 1
    assert detail["final_splits"] == []
    mock.update_transaction_splits.assert_not_awaited()


def test_split_dry_run_does_not_require_mutation_authorization() -> None:
    set_mutation_authorized(False)
    mock = client()
    mock.get_transaction_splits.return_value = payload()
    result = invoke(
        mock,
        [
            "replace",
            "--transaction-id",
            "txn-1",
            "--splits-json",
            '[{"merchantName":"Store","amount":-10.00,"categoryId":"cat-1"}]',
            "--dry-run",
        ],
    )
    assert result.exit_code == 0, result.output
    mock.update_transaction_splits.assert_not_awaited()
