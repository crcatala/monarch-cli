"""Guarded monthly category budget mutation service (mc-9u99).

One focused mutation: set the monthly amount for one category in one
explicitly identified month. The target is exactly one category and one
monthly budget period; reset, category-group budgets, flexible budgets,
future-month propagation, and rollover settings are deliberately out of scope
and are not representable through this surface.

Ordering is deliberate and matches the ticket contract: local validation
(identifier, date, amount) happens before authorization, client creation, and
any write; bounded read-only category discovery/validation happens before the
write attempt. The released public ``MonarchMoney.set_budget_amount``
capability is used with ``category_id``, the requested amount,
``timeframe="month"``, the requested start date, and ``apply_to_future=False``
only.

After a write attempt the exact category/month is read back through the
released ``get_budgets`` read capability and the observed planned amount is
compared against the requested amount using the documented currency
comparison below. The write result is never trusted for verification.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from ..core.exceptions import APIError, NotFoundError, ValidationError
from ..core.operations import Effect, Operation, run_mutation_call, run_read_call

#: Currency amount wire scale: budget amounts are compared and reported in
#: whole cents. A requested amount with more than this many decimal places is
#: rejected rather than silently rounded.
CURRENCY_SCALE = 2

#: Maximum number of significant digits accepted for a currency amount. This
#: keeps JSON output and the upstream GraphQL Float variable finite and
#: predictable.
CURRENCY_PRECISION = 18

#: Largest accepted absolute amount, mirroring the split-amount bound.
MAX_AMOUNT = Decimal("9999999999999999.99")

#: Documented currency comparison for readback verification: the requested and
#: observed amounts are both normalized to whole cents (``quantize`` to two
#: decimal places) and compared for exact equality. There is no tolerance
#: beyond cent normalization and no rounding of the requested value: an amount
#: that cannot be represented in cents is rejected during local validation.
CURRENCY_COMPARISON = "exact equality after normalizing both amounts to whole cents"

#: Descriptor for the read-only category-discovery call used to validate the
#: target category before a write. It never carries the remote_mutation effect.
DISCOVERY_OPERATION = Operation(
    command="budgets set category-discovery", effects=frozenset({Effect.READ_ONLY})
)

#: Descriptor for the bounded post-write readback used to verify the applied
#: amount. It never carries the remote_mutation effect.
READBACK_OPERATION = Operation(
    command="budgets set readback", effects=frozenset({Effect.READ_ONLY})
)


def parse_currency_amount(raw: str) -> Decimal:
    """Validate and normalize a requested budget amount.

    The value must be a finite, non-negative decimal with at most
    :data:`CURRENCY_SCALE` decimal places and at most
    :data:`CURRENCY_PRECISION` significant digits. A zero amount is valid and
    deliberately preserved (reset-to-zero), not treated as "no change".

    Args:
        raw: The raw ``--amount`` value.

    Returns:
        The amount normalized to whole cents.

    Raises:
        ValidationError: If the value is empty, non-finite, negative,
            over-precise, or too large.
    """
    if not isinstance(raw, str) or not raw.strip():
        raise ValidationError("--amount must be a non-empty number.", field="amount")
    try:
        parsed = Decimal(raw.strip())
    except (InvalidOperation, ValueError):
        raise ValidationError(
            f"--amount '{raw}' is not a valid number.",
            field="amount",
        ) from None
    if not parsed.is_finite():
        raise ValidationError("--amount must be a finite number.", field="amount")
    if parsed < 0:
        raise ValidationError(
            "--amount must not be negative; budgets are reset by setting zero.",
            field="amount",
            details={"value": raw},
        )
    exponent = parsed.as_tuple().exponent
    if isinstance(exponent, int) and exponent < -CURRENCY_SCALE:
        raise ValidationError(
            f"--amount supports at most {CURRENCY_SCALE} decimal places.",
            field="amount",
            details={"maximum_decimal_places": CURRENCY_SCALE},
        )
    if len(parsed.as_tuple().digits) > CURRENCY_PRECISION or abs(parsed) > MAX_AMOUNT:
        raise ValidationError(
            f"--amount exceeds {CURRENCY_PRECISION}-digit precision.",
            field="amount",
            details={"precision": CURRENCY_PRECISION},
        )
    normalized = parsed.quantize(Decimal("0.01"))
    # The released client serializes GraphQL Float variables as JSON numbers.
    # Reject values that the wire format would round silently; the requested
    # amount must reach the service unchanged (no silent rounding).
    if Decimal(str(float(normalized))) != normalized:
        raise ValidationError(
            "--amount cannot be represented exactly by the numeric wire format.",
            field="amount",
            details={"value": raw},
        )
    return normalized


def validate_month_start(parsed: date) -> None:
    """Require the monthly-period start date to be the first day of a month.

    Args:
        parsed: The already strictly parsed ``--start`` date.

    Raises:
        ValidationError: If the date is not the first of its month.
    """
    if parsed.day != 1:
        raise ValidationError(
            "--start must be the first day of a month (YYYY-MM-01) for a monthly budget.",
            field="start",
            details={"must_be_first_of_month": True},
        )


def validate_category_id(category_id: str) -> str:
    """Require a non-empty, whitespace-free-opaque category identifier.

    Args:
        category_id: The raw ``--category-id`` value.

    Returns:
        The unchanged identifier (identifiers are opaque and never coerced).

    Raises:
        ValidationError: If the identifier is empty or whitespace-only.
    """
    if not isinstance(category_id, str) or not category_id.strip():
        raise ValidationError(
            "--category-id must be a non-empty category ID.",
            field="category_id",
        )
    return category_id


def _as_object(value: Any, label: str) -> Mapping[str, Any]:
    """Coerce an upstream value to a mapping or raise a malformed-response error."""
    if not isinstance(value, Mapping):
        raise APIError(
            message=f"Malformed {label} response.",
            details={"expected": "object", "received": type(value).__name__},
        )
    return value


def find_category(client: Any, category_id: str) -> None:
    """Bounded read-only discovery that fails closed on an unknown category.

    The released ``get_transaction_categories`` capability is used as the
    single discovery surface. The matching category record must be a
    well-formed object whose ``id`` matches exactly; an unknown identifier is
    reported as not found and a malformed response is a typed API error so the
    caller never proceeds to a mutation attempt.

    Args:
        client: Authenticated client.
        category_id: Exact category target to validate.

    Raises:
        NotFoundError: If no discovered category matches the target.
        APIError: If the discovery response is malformed.
    """
    payload = run_read_call(lambda: client.get_transaction_categories(), DISCOVERY_OPERATION)
    response = _as_object(payload, "category discovery")
    categories = response.get("categories")
    if not isinstance(categories, list):
        raise APIError(
            message="Malformed category discovery response.",
            details={"expected": "list", "field": "categories"},
        )
    for record in categories:
        if not isinstance(record, Mapping):
            raise APIError(
                message="Malformed category discovery response.",
                details={"reason": "non_object_category"},
            )
        matched_id = record.get("id")
        if not isinstance(matched_id, str):
            raise APIError(
                message="Malformed category discovery response.",
                details={"reason": "missing_category_id"},
            )
        if matched_id == category_id:
            return
    raise NotFoundError(
        message=(
            "Unknown category; refusing to set a budget without an exact "
            "category target. Run 'monarch categories list' for valid IDs."
        ),
        resource_type="category",
        resource_id=category_id,
    )


def validate_budget_write_response(payload: Any) -> None:
    """Validate the budget mutation write response container.

    A GraphQL-level ``errors`` payload is a definitive rejection. A missing or
    malformed ``updateOrCreateBudgetItem.budgetItem`` result is reported as
    ambiguous, because the request was already dispatched and its remote
    effect cannot be established from the response. The write response is
    never used for verification; the authoritative readback follows separately.
    """
    from ..core.exceptions import MutationAmbiguousError

    response = _as_object(payload, "budget mutation")
    if response.get("errors"):
        raise APIError(
            message="The budget mutation was rejected by the service.",
            details={"reason": "graphql_errors"},
        )
    container = response.get("updateOrCreateBudgetItem")
    if not isinstance(container, Mapping):
        raise MutationAmbiguousError(
            "The budget write returned an incomplete response; remote state is unknown.",
            details={"reason": "malformed_response", "field": "updateOrCreateBudgetItem"},
        )
    budget_item = container.get("budgetItem")
    if not isinstance(budget_item, Mapping):
        raise MutationAmbiguousError(
            "The budget write returned no result; remote state is unknown.",
            details={"reason": "malformed_response", "field": "budgetItem"},
        )


def _observed_planned_amount(payload: Any, category_id: str, month: str) -> Decimal | None:
    """Read back the exact category/month planned amount.

    Args:
        payload: Raw ``get_budgets`` response.
        category_id: Exact category target.
        month: Exact ``YYYY-MM-01`` month to select.

    Returns:
        The observed planned amount normalized to cents, or ``None`` when the
        exact category/month record (or a usable amount) is unavailable.
    """
    if not isinstance(payload, Mapping):
        return None
    budget_data = payload.get("budgetData")
    if not isinstance(budget_data, Mapping):
        return None
    by_category = budget_data.get("monthlyAmountsByCategory")
    if not isinstance(by_category, list):
        return None
    for category_data in by_category:
        if not isinstance(category_data, Mapping):
            continue
        category = category_data.get("category")
        if not isinstance(category, Mapping) or category.get("id") != category_id:
            continue
        monthly_amounts = category_data.get("monthlyAmounts")
        if not isinstance(monthly_amounts, list):
            return None
        for amounts in monthly_amounts:
            if not isinstance(amounts, Mapping) or amounts.get("month") != month:
                continue
            return _normalize_observed(amounts.get("plannedCashFlowAmount"))
    return None


def _normalize_observed(value: Any) -> Decimal | None:
    """Normalize an observed upstream amount to cents, or ``None`` if unusable."""
    if isinstance(value, bool) or value is None:
        return None
    if not isinstance(value, (int, float, str)):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not parsed.is_finite():
        return None
    return parsed.quantize(Decimal("0.01"))


def read_back_planned_amount(client: Any, category_id: str, month: str) -> Decimal | None:
    """Bounded read-only readback of the exact category/month planned amount.

    The released ``get_budgets`` read capability is queried for the single
    target month only (``start_date == end_date``), so the readback is bounded
    to one monthly period.

    Args:
        client: Authenticated client.
        category_id: Exact category target.
        month: Exact ``YYYY-MM-01`` month.

    Returns:
        The observed planned amount normalized to cents, or ``None`` when the
        record is unavailable.

    Raises:
        NetworkError: On timeout or network failure.
        APIError: If the read call fails.
    """
    payload = run_read_call(
        lambda: client.get_budgets(start_date=month, end_date=month),
        READBACK_OPERATION,
    )
    return _observed_planned_amount(payload, category_id, month)


def set_monthly_category_budget(
    client: Any,
    *,
    category_id: str,
    amount: Decimal,
    month: str,
    operation: Operation,
) -> Any:
    """Dispatch the single-attempt budget write through the mutation boundary.

    Sends exactly the intended category target, amount, monthly timeframe,
    start date, and ``apply_to_future=False`` semantics. It never sends a
    category-group target or a future-month propagation flag.

    Args:
        client: Authenticated client.
        category_id: Exact category target.
        amount: Validated requested amount (whole cents).
        month: Exact ``YYYY-MM-01`` month.
        operation: Shared operation descriptor carrying ``remote_mutation``.

    Returns:
        The raw upstream mutation response.
    """
    return run_mutation_call(
        lambda: client.set_budget_amount(
            category_id=category_id,
            amount=float(amount),
            timeframe="month",
            start_date=month,
            apply_to_future=False,
        ),
        operation,
        entity_ids=(category_id,),
        verification=VERIFICATION_MESSAGE,
    )


#: Safe verification guidance for an ambiguous budget write. ``budgets list``
#: only reports the current month, so no tokenized command is offered for an
#: arbitrary requested month; the web UI is the honest verification surface.
VERIFICATION_MESSAGE = (
    "Confirm the category's monthly budget in the Monarch web UI before "
    "retrying; a timed-out write may already have applied the new amount and "
    "retrying could overwrite other changes."
)


__all__ = [
    "CURRENCY_SCALE",
    "CURRENCY_PRECISION",
    "MAX_AMOUNT",
    "CURRENCY_COMPARISON",
    "VERIFICATION_MESSAGE",
    "parse_currency_amount",
    "validate_month_start",
    "validate_category_id",
    "find_category",
    "read_back_planned_amount",
    "set_monthly_category_budget",
    "validate_budget_write_response",
]
