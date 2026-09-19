"""Read-only and guarded complete-set transaction split workflows."""

from __future__ import annotations

import json
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Annotated, Any, NoReturn

import typer

from ..core.adapter import get_authenticated_client
from ..core.error_handler import handle_errors
from ..core.exceptions import APIError, MutationAmbiguousError, NotFoundError, ValidationError
from ..core.mutation_outcomes import (
    ambiguous_item,
    build_mutation_outcome,
    error_from_exception,
    failed_item,
    succeeded_item,
    verification_object,
)
from ..core.operations import (
    Effect,
    Operation,
    operation_effects,
    require_mutation_authorization,
    run_mutation_call,
    run_read_call,
)
from ..output import OutputFormat, emit_mutation_outcome, output, validate_mutation_output
from .mutation_helpers import (
    as_object as _as_object,
)
from .mutation_helpers import (
    confirm_destructive,
)
from .mutation_helpers import (
    payload_error_details as _payload_errors,
)
from .mutation_helpers import (
    reject_positional_targets as _reject_positional_targets,
)
from .mutation_helpers import (
    validate_transaction_id as _validate_transaction_id,
)

app = typer.Typer(help="Inspect and safely replace transaction splits", no_args_is_help=True)

READ_EFFECTS: frozenset[Effect] = frozenset({Effect.READ_ONLY})
MUTATION_EFFECTS: frozenset[Effect] = frozenset({Effect.REMOTE_MUTATION})

# Split amounts are represented as signed cents.  This deliberately documented
# bound keeps JSON input and upstream requests finite and predictable.
DECIMAL_SCALE = 2
DECIMAL_PRECISION = 18
MAX_SPLITS = 100
MAX_INPUT_BYTES = 64 * 1024
MAX_MERCHANT_NAME_LENGTH = 200
MAX_CATEGORY_ID_LENGTH = 200
MAX_AMOUNT = Decimal("9999999999999999.99")
_WIRE_KEYS = frozenset({"merchantName", "amount", "categoryId"})

_VERIFICATION_COMMAND = ["monarch", "transactions", "splits", "show"]
_VERIFICATION_MESSAGE = (
    "Inspect the transaction's splits with 'monarch transactions splits show "
    "TRANSACTION_ID' and confirm the applied set before retrying."
)


def _as_transaction(payload: Any, transaction_id: str) -> Mapping[str, Any]:
    response = _as_object(payload, "transaction splits")
    transaction = response.get("getTransaction")
    if transaction is None:
        raise NotFoundError(
            message="Transaction not found.",
            resource_type="transaction",
            resource_id=transaction_id,
        )
    return _as_object(transaction, "transaction splits transaction")


def _decimal(value: Any, *, field: str, index: int | None = None) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValidationError(
            "Split amount must be a finite JSON number.",
            field=field,
            details={"index": index} if index is not None else None,
        )
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        parsed = Decimal("NaN")
    if not parsed.is_finite():
        raise ValidationError(
            "Split amount must be a finite decimal.",
            field=field,
            details={"index": index} if index is not None else None,
        )
    exponent = parsed.as_tuple().exponent
    if isinstance(exponent, int) and exponent < -DECIMAL_SCALE:
        raise ValidationError(
            f"Split amounts support at most {DECIMAL_SCALE} decimal places.",
            field=field,
            details={"index": index, "maximum_decimal_places": DECIMAL_SCALE},
        )
    digits = len(parsed.as_tuple().digits)
    if digits > DECIMAL_PRECISION or abs(parsed) > MAX_AMOUNT:
        raise ValidationError(
            f"Split amount exceeds {DECIMAL_PRECISION}-digit precision.",
            field=field,
            details={"index": index, "precision": DECIMAL_PRECISION},
        )
    return parsed.quantize(Decimal("0.01"))


def _normal_split(value: Any, index: int) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValidationError(
            "Each split must be an object.", field="splits", details={"index": index}
        )
    if set(value) != _WIRE_KEYS:
        raise ValidationError(
            "Each split must contain exactly merchantName, amount, and categoryId.",
            field="splits",
            details={
                "index": index,
                "required_fields": sorted(_WIRE_KEYS),
                "unsupported_fields": sorted(set(value) - _WIRE_KEYS),
            },
        )
    merchant = value.get("merchantName")
    category = value.get("categoryId")
    if not isinstance(merchant, str) or not merchant.strip():
        raise ValidationError(
            "merchantName must be a non-empty string.",
            field="merchantName",
            details={"index": index},
        )
    if len(merchant.strip()) > MAX_MERCHANT_NAME_LENGTH:
        raise ValidationError(
            f"merchantName must be at most {MAX_MERCHANT_NAME_LENGTH} characters.",
            field="merchantName",
            details={"index": index},
        )
    if not isinstance(category, str) or not category.strip():
        raise ValidationError(
            "categoryId must be a non-empty opaque string.",
            field="categoryId",
            details={"index": index},
        )
    if len(category) > MAX_CATEGORY_ID_LENGTH:
        raise ValidationError(
            f"categoryId must be at most {MAX_CATEGORY_ID_LENGTH} characters.",
            field="categoryId",
            details={"index": index},
        )
    raw_amount = value.get("amount")
    if not isinstance(raw_amount, Decimal):
        raise ValidationError(
            "amount must be a JSON number, not a string or boolean.",
            field="amount",
            details={"index": index},
        )
    amount = _decimal(raw_amount, field="amount", index=index)
    # The released client serializes GraphQL Float variables as JSON numbers.
    # Reject cents that would be rounded when converted to that wire type;
    # silently changing a split amount at the transport boundary is unsafe.
    wire_amount = float(amount)
    if Decimal(str(wire_amount)) != amount:
        raise ValidationError(
            "amount cannot be represented exactly by the numeric wire format.",
            field="amount",
            details={"index": index},
        )
    # Keep the public wire shape and avoid sending unsupported client fields.
    return {"merchantName": merchant.strip(), "amount": wire_amount, "categoryId": category}


def _reject_json_constant(_: str) -> NoReturn:
    raise ValueError("non-finite JSON number")


def _parse_json(text: str, source: str) -> Any:
    try:
        return json.loads(
            text,
            parse_float=Decimal,
            parse_int=Decimal,
            parse_constant=_reject_json_constant,
        )
    except (json.JSONDecodeError, ValueError):
        raise ValidationError(f"{source} must contain valid JSON.", field=source) from None


def _load_source(inline: str | None, file: Path | None) -> Any:
    if (inline is None) == (file is None):
        raise ValidationError(
            "Provide exactly one split source: --splits-json or --splits-file.",
            field="split_source",
        )
    if inline is not None:
        if len(inline.encode("utf-8")) > MAX_INPUT_BYTES:
            raise ValidationError(
                f"Inline split JSON must not exceed {MAX_INPUT_BYTES} bytes.",
                field="splits_json",
            )
        return _parse_json(inline, "--splits-json")
    assert file is not None
    try:
        if not file.is_file():
            raise OSError("not a regular file")
        if file.stat().st_size > MAX_INPUT_BYTES:
            raise ValidationError(
                f"Split file must not exceed {MAX_INPUT_BYTES} bytes.",
                field="splits_file",
            )
        text = file.read_text(encoding="utf-8")
    except ValidationError:
        raise
    except (OSError, UnicodeError):
        raise ValidationError(
            "Split file must be a readable UTF-8 JSON file.", field="splits_file"
        ) from None
    if len(text.encode("utf-8")) > MAX_INPUT_BYTES:
        raise ValidationError(
            f"Split file must not exceed {MAX_INPUT_BYTES} bytes.", field="splits_file"
        )
    return _parse_json(text, "--splits-file")


def _validate_splits(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValidationError("Split JSON must be an array.", field="splits")
    if not value:
        raise ValidationError(
            "Replacement requires at least one split; use the explicit clear "
            "operation for an empty set.",
            field="splits",
        )
    if len(value) > MAX_SPLITS:
        raise ValidationError(
            f"A replacement may contain at most {MAX_SPLITS} splits.",
            field="splits",
        )
    return [_normal_split(item, index) for index, item in enumerate(value)]


def _amount(value: Any, field: str = "amount") -> Decimal:
    return _decimal(value, field=field).quantize(Decimal("0.01"))


def _validate_signed_total(splits: list[dict[str, Any]], parent_amount: Any) -> None:
    parent = _amount(parent_amount, "parent_amount")
    amounts = [Decimal(str(item["amount"])) for item in splits]
    total = sum(amounts, Decimal("0.00")).quantize(Decimal("0.01"))
    if total != parent:
        raise ValidationError(
            "Split amounts must equal the signed parent transaction amount.",
            field="amount",
            details={
                "parent_amount": str(parent),
                "split_total": str(total),
                "precision": DECIMAL_SCALE,
            },
        )
    # Expenses are negative and income is positive. Zero-valued parents can
    # only be represented by zero-valued rows; mixed signs are not accepted.
    if parent < 0 and any(amount > 0 for amount in amounts):
        raise ValidationError("Expense splits must not contain positive amounts.", field="amount")
    if parent > 0 and any(amount < 0 for amount in amounts):
        raise ValidationError("Income splits must not contain negative amounts.", field="amount")
    if parent == 0 and any(amount != 0 for amount in amounts):
        raise ValidationError(
            "A zero-amount transaction requires zero-valued splits.", field="amount"
        )


def _normal_row(value: Any) -> dict[str, Any]:
    row = _as_object(value, "transaction split")
    return {
        "id": row.get("id"),
        "merchant_name": row.get("merchant", {}).get("name")
        if isinstance(row.get("merchant"), Mapping)
        else None,
        "category_id": row.get("category", {}).get("id")
        if isinstance(row.get("category"), Mapping)
        else None,
        "category_name": row.get("category", {}).get("name")
        if isinstance(row.get("category"), Mapping)
        else None,
        "amount": row.get("amount"),
        "notes": row.get("notes"),
    }


def _read_splits(
    client: Any, transaction_id: str
) -> tuple[Mapping[str, Any], list[dict[str, Any]]]:
    transaction = _as_transaction(
        run_read_call(
            lambda: client.get_transaction_splits(transaction_id=transaction_id),
            Operation(command="transactions splits show", effects=READ_EFFECTS),
        ),
        transaction_id,
    )
    rows = transaction.get("splitTransactions")
    if rows is None:
        rows = []
    if not isinstance(rows, list):
        raise APIError(
            "Malformed transaction splits response.", details={"field": "splitTransactions"}
        )
    return transaction, [_normal_row(row) for row in rows]


def _mutation_container(payload: Any) -> Mapping[str, Any]:
    response = _as_object(payload, "split mutation")
    if "errors" in response:
        errors = response["errors"]
        if not isinstance(errors, list):
            raise APIError(
                "The split mutation returned an invalid error payload.",
                details={"field": "errors"},
            )
        if errors:
            raise APIError(
                "The split mutation was rejected by the service.",
                details={"payload_errors": _payload_errors(errors)},
            )
    container = response.get("updateTransactionSplit")
    if not isinstance(container, Mapping):
        raise APIError(
            "The split mutation returned no result.", details={"field": "updateTransactionSplit"}
        )
    # The released client/API returns null, rather than [], when the
    # nullable payload-error field has no errors. A missing or otherwise
    # malformed field is different: the request was already dispatched and
    # its remote outcome cannot be established safely.
    if "errors" not in container:
        raise MutationAmbiguousError(
            "The split write returned an incomplete response; remote state is unknown.",
            details={"reason": "malformed_response", "field": "updateTransactionSplit.errors"},
        )
    errors = container["errors"]
    if errors is None:
        errors = []
    elif not isinstance(errors, list):
        raise MutationAmbiguousError(
            "The split write returned a malformed response; remote state is unknown.",
            details={"reason": "malformed_response", "field": "updateTransactionSplit.errors"},
        )
    if errors:
        raise APIError(
            "The split mutation was rejected by the service.",
            details={"payload_errors": _payload_errors(errors)},
        )
    if not isinstance(container.get("transaction"), Mapping):
        raise MutationAmbiguousError(
            "The split write returned no transaction result; remote state is unknown.",
            details={"reason": "malformed_response", "field": "updateTransactionSplit.transaction"},
        )
    return container


def _emit(outcome: dict[str, Any]) -> None:
    emit_mutation_outcome(outcome)


def _confirm(operation: str, transaction_id: str, requested: list[dict[str, Any]]) -> None:
    confirm_destructive(
        f"Replace all splits on transaction {transaction_id} with {len(requested)} row(s)?",
        operation=operation,
    )


def _verify(
    client: Any, transaction_id: str, requested: list[dict[str, Any]]
) -> dict[str, Any] | None:
    _observed_parent, observed = _read_splits(client, transaction_id)
    if len(observed) != len(requested):
        return {"expected_count": len(requested), "observed_count": len(observed)}
    for index, (expected, actual) in enumerate(zip(requested, observed, strict=True)):
        try:
            expected_amount = _amount(expected["amount"])
            actual_amount = _amount(actual["amount"])
        except ValidationError:
            return {"index": index, "reason": "malformed_observed_amount"}
        if (
            expected["merchantName"] != actual["merchant_name"]
            or expected["categoryId"] != actual["category_id"]
            or expected_amount != actual_amount
        ):
            mismatched_fields = []
            if expected["merchantName"] != actual["merchant_name"]:
                mismatched_fields.append("merchantName")
            if expected["categoryId"] != actual["category_id"]:
                mismatched_fields.append("categoryId")
            if expected_amount != actual_amount:
                mismatched_fields.append("amount")
            return {
                "index": index,
                "mismatched_fields": mismatched_fields,
                "reason": "verification_mismatch",
            }
    return None


@app.command("show")
@handle_errors
@operation_effects(Effect.READ_ONLY)
def show_splits(
    transaction_id: Annotated[str, typer.Argument(help="Transaction ID")],
    format: Annotated[OutputFormat | None, typer.Option("-f", "--format")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
    raw: Annotated[bool, typer.Option("--raw")] = False,
) -> None:
    """Show a transaction's parent amount and current split rows."""
    _validate_transaction_id(transaction_id)
    client = get_authenticated_client()
    payload = run_read_call(
        lambda: client.get_transaction_splits(transaction_id=transaction_id),
        Operation(command="transactions splits show", effects=READ_EFFECTS),
    )
    if raw:
        output(payload, OutputFormat.JSON if json_output else format)
        return
    transaction = _as_transaction(payload, transaction_id)
    rows = transaction.get("splitTransactions")
    if rows is None:
        rows = []
    if not isinstance(rows, list):
        raise APIError(
            "Malformed transaction splits response.", details={"field": "splitTransactions"}
        )
    output(
        {
            "transaction_id": transaction_id,
            "returned_transaction_id": transaction.get("id"),
            "amount": transaction.get("amount"),
            "merchant_name": transaction.get("merchant", {}).get("name")
            if isinstance(transaction.get("merchant"), Mapping)
            else None,
            "category_id": transaction.get("category", {}).get("id")
            if isinstance(transaction.get("category"), Mapping)
            else None,
            "splits": [_normal_row(row) for row in rows],
        },
        OutputFormat.JSON if json_output else format,
    )


@app.command("replace", context_settings={"allow_extra_args": True})
@handle_errors
@operation_effects(Effect.REMOTE_MUTATION)
def replace_splits(
    ctx: typer.Context,
    transaction_id: Annotated[str, typer.Option("--transaction-id", help="Transaction ID")],
    splits_json: Annotated[
        str | None,
        typer.Option("--splits-json", help="Inline split JSON array"),
    ] = None,
    splits_file: Annotated[
        Path | None,
        typer.Option("--splits-file", help="Readable JSON file containing a split array"),
    ] = None,
) -> None:
    """Replace every split using one bounded JSON source."""
    _reject_positional_targets(ctx.args)
    _validate_transaction_id(transaction_id)
    requested = _validate_splits(_load_source(splits_json, splits_file))
    operation = Operation(command="transactions splits replace", effects=MUTATION_EFFECTS)
    validate_mutation_output()
    require_mutation_authorization(operation)
    client = get_authenticated_client()
    # This read is intentionally before confirmation and the mutation: parent
    # amount validation must use the current server value, not caller input.
    parent, _current = _read_splits(client, transaction_id)
    _validate_signed_total(requested, parent.get("amount"))
    _confirm(operation.command, transaction_id, requested)
    try:
        payload = run_mutation_call(
            lambda: client.update_transaction_splits(
                transaction_id=transaction_id, split_data=requested
            ),
            operation,
            entity_ids=(transaction_id,),
            verification=_VERIFICATION_MESSAGE,
        )
        _mutation_container(payload)
        try:
            mismatch = _verify(client, transaction_id, requested)
        except Exception:
            _emit(
                build_mutation_outcome(
                    operation.command,
                    [
                        ambiguous_item(
                            "transaction",
                            transaction_id,
                            "The split write succeeded remotely but could not be "
                            "verified; remote state is unknown.",
                            {"reason": "verification_unavailable", "remote_state": "unknown"},
                        )
                    ],
                    verification=verification_object(
                        _VERIFICATION_MESSAGE, command=[*_VERIFICATION_COMMAND, transaction_id]
                    ),
                )
            )
            return
        if mismatch is not None:
            _emit(
                build_mutation_outcome(
                    operation.command,
                    [
                        ambiguous_item(
                            "transaction",
                            transaction_id,
                            "The split write returned a different set than "
                            "requested; remote state is unknown.",
                            {
                                "reason": "verification_mismatch",
                                **mismatch,
                                "remote_state": "unknown",
                            },
                        )
                    ],
                    verification=verification_object(
                        _VERIFICATION_MESSAGE, command=[*_VERIFICATION_COMMAND, transaction_id]
                    ),
                )
            )
            return
        _emit(
            build_mutation_outcome(
                operation.command,
                [succeeded_item("transaction", transaction_id, {"split_count": len(requested)})],
            )
        )
    except typer.Exit:
        raise
    except MutationAmbiguousError as exc:
        _emit(
            build_mutation_outcome(
                operation.command,
                [
                    ambiguous_item(
                        "transaction",
                        transaction_id,
                        exc.message,
                        {"remote_state": "unknown", "reason": exc.details.get("reason")},
                    )
                ],
                verification=verification_object(
                    _VERIFICATION_MESSAGE, command=[*_VERIFICATION_COMMAND, transaction_id]
                ),
            )
        )
    except Exception as exc:
        error = error_from_exception(exc)
        _emit(
            build_mutation_outcome(
                operation.command,
                [
                    failed_item(
                        "transaction",
                        transaction_id,
                        error["code"],
                        error["message"],
                        error["details"],
                    )
                ],
            )
        )


@app.command("clear", context_settings={"allow_extra_args": True})
@handle_errors
@operation_effects(Effect.REMOTE_MUTATION)
def clear_splits(
    ctx: typer.Context,
    transaction_id: Annotated[str, typer.Option("--transaction-id", help="Transaction ID")],
) -> None:
    """Explicitly clear every split by sending the canonical empty list."""
    _reject_positional_targets(ctx.args)
    _validate_transaction_id(transaction_id)
    operation = Operation(command="transactions splits clear", effects=MUTATION_EFFECTS)
    validate_mutation_output()
    require_mutation_authorization(operation)
    client = get_authenticated_client()
    _confirm(operation.command, transaction_id, [])
    try:
        payload = run_mutation_call(
            lambda: client.update_transaction_splits(transaction_id=transaction_id, split_data=[]),
            operation,
            entity_ids=(transaction_id,),
            verification=_VERIFICATION_MESSAGE,
        )
        _mutation_container(payload)
        try:
            _parent, observed = _read_splits(client, transaction_id)
        except Exception:
            _emit(
                build_mutation_outcome(
                    operation.command,
                    [
                        ambiguous_item(
                            "transaction",
                            transaction_id,
                            "The clear write succeeded remotely but could not be "
                            "verified; remote state is unknown.",
                            {"reason": "verification_unavailable", "remote_state": "unknown"},
                        )
                    ],
                    verification=verification_object(
                        _VERIFICATION_MESSAGE, command=[*_VERIFICATION_COMMAND, transaction_id]
                    ),
                )
            )
            return
        if observed:
            _emit(
                build_mutation_outcome(
                    operation.command,
                    [
                        ambiguous_item(
                            "transaction",
                            transaction_id,
                            "The clear response could not be verified; remote state is unknown.",
                            {
                                "reason": "verification_mismatch",
                                "observed_count": len(observed),
                                "remote_state": "unknown",
                            },
                        )
                    ],
                    verification=verification_object(
                        _VERIFICATION_MESSAGE, command=[*_VERIFICATION_COMMAND, transaction_id]
                    ),
                )
            )
            return
        _emit(
            build_mutation_outcome(
                operation.command,
                [succeeded_item("transaction", transaction_id, {"split_count": 0})],
            )
        )
    except typer.Exit:
        raise
    except MutationAmbiguousError as exc:
        _emit(
            build_mutation_outcome(
                operation.command,
                [
                    ambiguous_item(
                        "transaction",
                        transaction_id,
                        exc.message,
                        {"remote_state": "unknown", "reason": exc.details.get("reason")},
                    )
                ],
                verification=verification_object(
                    _VERIFICATION_MESSAGE, command=[*_VERIFICATION_COMMAND, transaction_id]
                ),
            )
        )
    except Exception as exc:
        error = error_from_exception(exc)
        _emit(
            build_mutation_outcome(
                operation.command,
                [
                    failed_item(
                        "transaction",
                        transaction_id,
                        error["code"],
                        error["message"],
                        error["details"],
                    )
                ],
            )
        )
