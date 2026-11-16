"""Receipt attachments and missing-document workflows."""

from datetime import date
from enum import Enum
from typing import Annotated, Any

import typer

from ..core.adapter import get_authenticated_client
from ..core.async_utils import run_api_call
from ..core.error_handler import handle_errors
from ..core.exceptions import APIError, NetworkError
from ..core.receipt_api import fetch_inbox, fetch_receipt, match_receipt
from ..output import OutputFormat, output
from ..transformers.transactions import transform_transactions
from .transactions import attach

app = typer.Typer(help="Receipt attachments, scanned inbox, and matching", no_args_is_help=True)
app.command("upload")(attach)


@app.command("list")
@handle_errors
def list_receipts(
    transaction_id: Annotated[str, typer.Argument(help="Transaction ID")],
    format: Annotated[OutputFormat | None, typer.Option("--format", "-f")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """List attachment metadata and asset URLs for one transaction."""
    client = get_authenticated_client()
    data: Any = run_api_call(
        lambda: client.get_transaction_details(transaction_id=transaction_id, redirect_posted=True)
    )
    transaction = data.get("getTransaction") if isinstance(data, dict) else None
    attachments = transaction.get("attachments") if isinstance(transaction, dict) else None
    if not isinstance(attachments, list) or any(not isinstance(a, dict) for a in attachments):
        raise ValueError("Transaction response is missing valid attachment data")
    output(attachments, OutputFormat.JSON if json_output else format)


@app.command("missing")
@handle_errors
def missing(
    account: Annotated[list[str] | None, typer.Option("--account", "-a")] = None,
    start: Annotated[str | None, typer.Option("--start", help="Start date (YYYY-MM-DD)")] = None,
    end: Annotated[str | None, typer.Option("--end", help="End date (YYYY-MM-DD)")] = None,
    limit: Annotated[int, typer.Option("--limit", "-l", min=1)] = 100,
    offset: Annotated[int, typer.Option("--offset", "-o", min=0)] = 0,
    format: Annotated[OutputFormat | None, typer.Option("--format", "-f")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """List one page of transactions with no attachments; does not imply a receipt is required."""
    for value in (start, end):
        if value is not None:
            date.fromisoformat(value)
    if start and end and date.fromisoformat(start) > date.fromisoformat(end):
        raise ValueError("Start date must be on or before end date")
    client = get_authenticated_client()
    data: Any = run_api_call(
        lambda: client.get_transactions(
            has_attachments=False,
            account_ids=account or [],
            start_date=start,
            end_date=end,
            limit=limit,
            offset=offset,
        )
    )
    page = data.get("allTransactions") if isinstance(data, dict) else None
    results = page.get("results") if isinstance(page, dict) else None
    if not isinstance(results, list) or any(not isinstance(row, dict) for row in results):
        raise ValueError("Transaction response is missing valid results")
    output(transform_transactions(data), OutputFormat.JSON if json_output else format)


class ReceiptStatus(str, Enum):
    """Processing states observed in Monarch's web client."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    PENDING_MATCHES = "pending_matches"
    COMPLETED = "completed"
    FAILED = "failed"


class ReceiptOrder(str, Enum):
    """Server-side receipt ordering."""

    RECEIPT_DATE = "receipt_date"
    UPLOAD_DATE = "upload_date"


@app.command("inbox")
@handle_errors
def inbox(
    status: Annotated[ReceiptStatus | None, typer.Option("--status")] = None,
    order_by: Annotated[ReceiptOrder, typer.Option("--order-by")] = ReceiptOrder.RECEIPT_DATE,
    limit: Annotated[int, typer.Option("--limit", "-l", min=1)] = 25,
    offset: Annotated[int, typer.Option("--offset", "-o", min=0)] = 0,
    format: Annotated[OutputFormat | None, typer.Option("--format", "-f")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """List one page of image/email receipts with processing status and match details."""
    client = get_authenticated_client()
    data = run_api_call(
        lambda: fetch_inbox(
            client,
            limit=limit,
            offset=offset,
            status=status.value if status is not None else None,
            order_by=order_by.value,
        )
    )
    output(data, OutputFormat.JSON if json_output else format)


@app.command("show")
@handle_errors
def show(
    receipt_id: Annotated[str, typer.Argument(help="Scanned receipt ID from receipts inbox")],
    format: Annotated[OutputFormat | None, typer.Option("--format", "-f")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Inspect scanned receipt status, line items, and retail transaction IDs."""
    client = get_authenticated_client()
    data = run_api_call(lambda: fetch_receipt(client, receipt_id))
    output(data, OutputFormat.JSON if json_output else format)


@app.command("match")
@handle_errors
def match(
    receipt_id: Annotated[str, typer.Argument(help="Scanned receipt ID from receipts inbox")],
    transaction_id: Annotated[str, typer.Argument(help="Existing Monarch transaction ID")],
    retail_transaction: Annotated[
        str | None,
        typer.Option(
            "--retail-transaction", help="Required when receipt has multiple transactions"
        ),
    ] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Read and validate both targets without matching")
    ] = False,
    format: Annotated[OutputFormat | None, typer.Option("--format", "-f")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Match a scanned receipt to a transaction and verify the link.

    Monarch can update notes, categories, and splits according to receipt settings.
    Use --dry-run first to inspect both targets. No automatic retries are made.
    """
    client = get_authenticated_client()
    try:
        data = run_api_call(
            lambda: match_receipt(
                client,
                receipt_id,
                transaction_id,
                retail_transaction_id=retail_transaction,
                dry_run=dry_run,
            ),
            max_retries=0,
        )
    except NetworkError as exc:
        raise APIError(
            "Receipt matching request failed; inspect receipts show before retrying. "
            "A submitted match may have completed.",
            details={"receipt_id": receipt_id, "transaction_id": transaction_id, "cause": str(exc)},
        ) from exc
    output(data, OutputFormat.JSON if json_output else format)
