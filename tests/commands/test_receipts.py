"""Receipt command contracts; no live API calls."""

import json
from unittest.mock import AsyncMock, patch

import pytest
from typer.testing import CliRunner

from monarch_cli.main import app

runner = CliRunner()


@pytest.mark.parametrize("attachments", [[], [{"id": "a1", "filename": "shop.pdf"}]])
def test_list_receipts(attachments):
    with patch("monarch_cli.commands.receipts.get_authenticated_client") as get_client:
        get_client.return_value.get_transaction_details = AsyncMock(
            return_value={"getTransaction": {"id": "t1", "attachments": attachments}}
        )
        result = runner.invoke(app, ["receipts", "list", "t1", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == attachments


@pytest.mark.parametrize("payload", [{}, {"getTransaction": None}, {"getTransaction": {}}])
def test_list_rejects_missing_attachment_data(payload):
    with patch("monarch_cli.commands.receipts.get_authenticated_client") as get_client:
        get_client.return_value.get_transaction_details = AsyncMock(return_value=payload)
        result = runner.invoke(app, ["receipts", "list", "t1", "--json"])
    assert result.exit_code == 1
    assert json.loads(result.stdout)["error"] is True


def test_missing_filters_and_pagination():
    with patch("monarch_cli.commands.receipts.get_authenticated_client") as get_client:
        method = AsyncMock(return_value={"allTransactions": {"results": []}})
        get_client.return_value.get_transactions = method
        result = runner.invoke(
            app,
            [
                "receipts",
                "missing",
                "--account",
                "acc1",
                "--limit",
                "5",
                "--offset",
                "10",
                "--start",
                "2026-11-01",
                "--end",
                "2026-11-15",
                "--json",
            ],
        )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == []
    assert method.call_args.kwargs == {
        "has_attachments": False,
        "account_ids": ["acc1"],
        "limit": 5,
        "offset": 10,
        "start_date": "2026-11-01",
        "end_date": "2026-11-15",
    }


@pytest.mark.parametrize("args", [["--limit", "0"], ["--offset", "-1"], ["--start", "bad"]])
def test_missing_invalid_input(args):
    with patch("monarch_cli.commands.receipts.get_authenticated_client") as get_client:
        result = runner.invoke(app, ["receipts", "missing", *args])
    assert result.exit_code != 0
    get_client.assert_not_called()


def test_upload_preview(tmp_path):
    receipt = tmp_path / "receipt.pdf"
    receipt.write_bytes(b"%PDF test")
    with patch("monarch_cli.commands.transactions.get_authenticated_client") as get_client:
        result = runner.invoke(
            app, ["receipts", "upload", "t1", str(receipt), "--dry-run", "--json"]
        )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["status"] == "dry_run"
    get_client.assert_not_called()


@pytest.mark.parametrize("payload", [{}, {"allTransactions": None}])
def test_missing_rejects_incomplete_response(payload):
    with patch("monarch_cli.commands.receipts.get_authenticated_client") as get_client:
        get_client.return_value.get_transactions = AsyncMock(return_value=payload)
        result = runner.invoke(app, ["receipts", "missing", "--json"])
    assert result.exit_code == 1
    assert json.loads(result.stdout)["error"] is True


def test_list_api_failure():
    with patch("monarch_cli.commands.receipts.get_authenticated_client") as get_client:
        get_client.return_value.get_transaction_details = AsyncMock(
            side_effect=RuntimeError("service unavailable")
        )
        result = runner.invoke(app, ["receipts", "list", "t1", "--json"])
    assert result.exit_code == 1
    assert "service unavailable" in json.loads(result.stdout)["message"]


def test_scanned_inbox_options():
    with (
        patch("monarch_cli.commands.receipts.get_authenticated_client"),
        patch("monarch_cli.commands.receipts.fetch_inbox", new_callable=AsyncMock) as fetch,
    ):
        fetch.return_value = {"results": [], "total_count": 0, "next_offset": None}
        result = runner.invoke(
            app,
            [
                "receipts",
                "inbox",
                "--status",
                "pending_matches",
                "--order-by",
                "upload_date",
                "--limit",
                "2",
                "--offset",
                "4",
                "--json",
            ],
        )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["total_count"] == 0
    assert fetch.call_args.kwargs == {
        "status": "pending_matches",
        "order_by": "upload_date",
        "limit": 2,
        "offset": 4,
    }


def test_scanned_show():
    with (
        patch("monarch_cli.commands.receipts.get_authenticated_client"),
        patch("monarch_cli.commands.receipts.fetch_receipt", new_callable=AsyncMock) as fetch,
    ):
        fetch.return_value = {"id": "r1", "status": "in_progress"}
        result = runner.invoke(app, ["receipts", "show", "r1", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["status"] == "in_progress"
    assert fetch.call_args.args[1] == "r1"


@pytest.mark.parametrize(
    "args",
    [
        ["--status", "invalid"],
        ["--order-by", "invalid"],
        ["--limit", "0"],
        ["--offset", "-1"],
    ],
)
def test_scanned_inbox_rejects_bad_options(args):
    with patch("monarch_cli.commands.receipts.get_authenticated_client") as get_client:
        result = runner.invoke(app, ["receipts", "inbox", *args])
    assert result.exit_code == 2
    get_client.assert_not_called()


@pytest.mark.parametrize("preview", [True, False])
def test_scanned_match_does_not_retry_writes(preview):
    from monarch_cli.core.async_utils import run_api_call

    with (
        patch("monarch_cli.commands.receipts.get_authenticated_client"),
        patch("monarch_cli.commands.receipts.match_receipt", new_callable=AsyncMock) as match,
        patch("monarch_cli.commands.receipts.run_api_call", wraps=run_api_call) as run,
    ):
        match.return_value = {
            "status": "dry_run" if preview else "matched",
            "verified": not preview,
        }
        args = ["receipts", "match", "r1", "t1", "--retail-transaction", "rt1", "--json"]
        if preview:
            args.append("--dry-run")
        result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert match.call_args.kwargs == {"retail_transaction_id": "rt1", "dry_run": preview}
    assert run.call_args.kwargs["max_retries"] == 0


def test_scanned_match_timeout_is_not_retried():
    with (
        patch("monarch_cli.commands.receipts.get_authenticated_client"),
        patch("monarch_cli.commands.receipts.match_receipt", new_callable=AsyncMock) as match,
    ):
        match.side_effect = TimeoutError("uncertain result")
        result = runner.invoke(app, ["receipts", "match", "r1", "t1", "--json"])
    assert result.exit_code == 1
    assert json.loads(result.stdout)["error"] is True
    assert match.await_count == 1
