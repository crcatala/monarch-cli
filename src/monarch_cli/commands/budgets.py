"""Budget commands for Monarch CLI."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

import typer

from ..core.adapter import get_authenticated_client
from ..core.dates import parse_iso_date
from ..core.error_handler import handle_errors
from ..core.exceptions import MutationAmbiguousError, ValidationError
from ..core.mutation_outcomes import (
    ambiguous_item,
    build_mutation_outcome,
    error_from_exception,
    failed_item,
    outcome_operation,
    succeeded_item,
    verification_object,
)
from ..core.operations import (
    Effect,
    Operation,
    operation_effects,
    require_mutation_authorization,
    resolve_invocation,
    run_read_call,
)
from ..output import OutputFormat, emit_mutation_outcome, output, validate_mutation_output
from ..output.progress import spinner
from ..services.budgets import (
    VERIFICATION_MESSAGE,
    find_category,
    parse_currency_amount,
    read_back_planned_amount,
    set_monthly_category_budget,
    validate_budget_write_response,
    validate_category_id,
    validate_month_start,
)

app = typer.Typer(
    help="Budget management",
    no_args_is_help=True,
)

READ_EFFECTS: frozenset[Effect] = frozenset({Effect.READ_ONLY})
MUTATION_EFFECTS: frozenset[Effect] = frozenset({Effect.REMOTE_MUTATION})


def _reject_positional_targets(legacy: list[str] | None) -> None:
    """Reject a positional mutation target with an actionable error.

    ``budgets set`` is option-scoped only: it never accepts a positional
    category, amount, or date.
    """
    if legacy:
        raise ValidationError(
            "Positional targets are not supported; use --category-id, --amount, and --start.",
            field="category_id",
            details={"removed_positional": True},
        )


def _build_budget_preview(category_id: str, month: str, amount: str) -> dict[str, Any]:
    """Build the dry-run preview for the one-category/one-month scope."""
    return {
        "status": "dry_run",
        "operation": outcome_operation("budgets set"),
        "target": {"category_id": category_id, "start": month},
        "detail": {
            "category_id": category_id,
            "month": month,
            "amount": amount,
            "timeframe": "month",
            "apply_to_future": False,
        },
    }


def _transform_budgets(raw_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Transform raw budget API response to simplified format.

    The API returns monthlyAmountsByCategory with nested monthlyAmounts arrays.
    We extract the current month's data for each category.

    Args:
        raw_data: Raw API response from get_budgets()

    Returns:
        List of budget items with category_id, budgeted, spent, remaining
    """
    result = []
    budget_data = raw_data.get("budgetData", {})
    monthly_by_category = budget_data.get("monthlyAmountsByCategory", [])

    # Get current month in YYYY-MM-01 format to match API
    current_month = date.today().replace(day=1).isoformat()

    for category_data in monthly_by_category:
        category = category_data.get("category", {})
        category_id = category.get("id")
        monthly_amounts = category_data.get("monthlyAmounts", [])

        # Find current month's amounts
        current_amounts = None
        for amounts in monthly_amounts:
            if amounts.get("month") == current_month:
                current_amounts = amounts
                break

        # Fall back to first month if current not found
        if current_amounts is None and monthly_amounts:
            current_amounts = monthly_amounts[0]

        if current_amounts:
            budgeted = current_amounts.get("plannedCashFlowAmount", 0) or 0
            actual = current_amounts.get("actualAmount", 0) or 0
            remaining = current_amounts.get("remainingAmount", 0) or 0

            # Only include categories with budget or spending
            if budgeted != 0 or actual != 0:
                result.append(
                    {
                        "category_id": category_id,
                        "budgeted": budgeted,
                        "spent": abs(actual),  # Show as positive
                        "remaining": remaining,
                    }
                )

    return result


@app.command("list")
@handle_errors
@operation_effects(Effect.READ_ONLY)
def list_cmd(
    format: Annotated[
        OutputFormat | None,
        typer.Option(
            "-f",
            "--format",
            help="Output format (plain, json, table, csv, compact)",
        ),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Output as JSON (shortcut for --format json)",
        ),
    ] = False,
) -> None:
    """List budget status with spent/remaining amounts.

    Shows all budget categories with their allocated amount, spending,
    and remaining balance. Spent amounts are shown as positive numbers.

    Examples:
        monarch budgets list                # Plain format (default in terminal)
        monarch budgets list --json         # JSON format
        monarch budgets list --format table # Table format
        monarch budgets list | jq .         # Auto-JSON when piped
        monarch budgets list | jq '[.[] | select(.remaining < 0)]'  # Over budget
    """
    # Determine output format
    output_format = format
    if json_output:
        output_format = OutputFormat.JSON

    with spinner("Fetching budgets..."):
        client = get_authenticated_client()
        raw_data: dict[str, Any] = run_read_call(
            lambda: client.get_budgets(),
            Operation(command="budgets list", effects=frozenset({Effect.READ_ONLY})),
        )

        # Transform to simplified format
        data = _transform_budgets(raw_data)

    output(data, output_format)


@app.command("set", context_settings={"allow_extra_args": True})
@handle_errors
@operation_effects(Effect.REMOTE_MUTATION)
def set_budget(
    ctx: typer.Context,
    category_id: Annotated[
        str,
        typer.Option("--category-id", help="Category ID to set the monthly budget for"),
    ],
    amount: Annotated[
        str,
        typer.Option("--amount", help="Monthly amount (finite, non-negative, max 2 decimals)"),
    ],
    start: Annotated[
        str,
        typer.Option("--start", help="Monthly period start, first day YYYY-MM-01"),
    ],
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview without writing"),
    ] = False,
) -> None:
    """Set the monthly amount for one category in one explicitly identified month.

    This one-category/one-month scope never propagates to future months,
    targets a category group, updates flexible budgets, resets an entire
    budget, or changes rollover settings. A zero amount is a deliberate
    reset-to-zero for the category; negative amounts are rejected.

    This remote mutation requires the global --allow-mutations option, placed
    before the command path. The exact category is validated against
    read-only category discovery before the write. After the write, the exact
    category/month planned amount is read back and compared against the
    requested amount. Use --dry-run to validate and preview without writing.

    Examples:
        monarch --allow-mutations budgets set \\
            --category-id CAT123 --amount 500.00 --start 2026-09-01
        monarch budgets set --category-id CAT123 --amount 500.00 --start 2026-09-01 --dry-run
    """
    _reject_positional_targets(ctx.args)

    # Local validation (identifier, date, amount) precedes authorization,
    # client creation, and every API call.
    validate_category_id(category_id)
    parsed_start = parse_iso_date(start, field="start")
    assert parsed_start is not None  # required option; parse_iso_date returns a date
    validate_month_start(parsed_start)
    requested = parse_currency_amount(amount)
    month = parsed_start.isoformat()

    operation = resolve_invocation("budgets set", MUTATION_EFFECTS, dry_run=dry_run)
    validate_mutation_output()
    if not dry_run:
        require_mutation_authorization(operation)

    client = get_authenticated_client()
    # Bounded read-only category discovery precedes the write attempt; an
    # unknown or malformed category fails closed without a mutation attempt.
    find_category(client, category_id)

    if dry_run:
        emit_mutation_outcome(_build_budget_preview(category_id, month, str(requested)))
        return

    try:
        payload = set_monthly_category_budget(
            client,
            category_id=category_id,
            amount=requested,
            month=month,
            operation=operation,
        )
        validate_budget_write_response(payload)
        try:
            observed = read_back_planned_amount(client, category_id, month)
        except Exception:  # noqa: BLE001 - unverified write is ambiguous
            observed = None
        if observed is None:
            emit_mutation_outcome(
                build_mutation_outcome(
                    "budgets set",
                    [
                        ambiguous_item(
                            "budget",
                            category_id,
                            "The budget write succeeded remotely but could not be "
                            "verified; remote state is unknown.",
                            {
                                "reason": "verification_unavailable",
                                "remote_state": "unknown",
                                "category_id": category_id,
                                "month": month,
                                "requested_amount": str(requested),
                            },
                        )
                    ],
                    verification=verification_object(VERIFICATION_MESSAGE),
                )
            )
            return
        if observed != requested:
            emit_mutation_outcome(
                build_mutation_outcome(
                    "budgets set",
                    [
                        ambiguous_item(
                            "budget",
                            category_id,
                            "The budget write could not be verified as requested; "
                            "remote state is unknown.",
                            {
                                "reason": "verification_mismatch",
                                "remote_state": "unknown",
                                "category_id": category_id,
                                "month": month,
                                "requested_amount": str(requested),
                                "observed_amount": str(observed),
                            },
                        )
                    ],
                    verification=verification_object(VERIFICATION_MESSAGE),
                )
            )
            return
        emit_mutation_outcome(
            build_mutation_outcome(
                "budgets set",
                [
                    succeeded_item(
                        "budget",
                        category_id,
                        {
                            "category_id": category_id,
                            "month": month,
                            "requested_amount": str(requested),
                            "observed_amount": str(observed),
                            "timeframe": "month",
                        },
                    )
                ],
            )
        )
    except typer.Exit:
        raise
    except MutationAmbiguousError as exc:
        emit_mutation_outcome(
            build_mutation_outcome(
                "budgets set",
                [
                    ambiguous_item(
                        "budget",
                        category_id,
                        exc.message,
                        {
                            "reason": exc.details.get("reason"),
                            "remote_state": "unknown",
                            "category_id": category_id,
                            "month": month,
                            "requested_amount": str(requested),
                        },
                    )
                ],
                verification=verification_object(VERIFICATION_MESSAGE),
            )
        )
    except Exception as exc:  # noqa: BLE001 - classified by the contract
        error = error_from_exception(exc)
        emit_mutation_outcome(
            build_mutation_outcome(
                "budgets set",
                [
                    failed_item(
                        "budget",
                        category_id,
                        error["code"],
                        error["message"],
                        error["details"],
                    )
                ],
            )
        )
