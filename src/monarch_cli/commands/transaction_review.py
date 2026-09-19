"""Intent-oriented, guarded transaction review-state mutations (mc-e49c).

Two explicit operations, one transaction target each, selected with a required
``--transaction-id`` option (never a positional argument):

- ``transactions review mark``     -> mark one transaction reviewed
- ``transactions review return``   -> return one transaction to the review queue

The upstream ``reviewed`` and ``needsReview`` inputs are not interchangeable,
so users never supply a pair of review booleans. Each intent maps to exactly one
input field and the CLI never sends ``reviewed=False`` or ``needsReview=False``:

- mark reviewed sends ``reviewed=True`` and omits ``needsReview``;
- return to queue sends ``needsReview=True`` and omits ``reviewed``.

The write goes through a narrow local GraphQL adapter
(:mod:`monarch_cli.core.review_mutation`) that serializes only transaction
identity and the one intended field; the released upstream helper would also
send ``category: null`` and ``name: null``. Before writing, the transaction is
read (no pending redirect) to verify exact identity and detect an
already-satisfied no-op. After writing, the detail is read again to confirm the
intended review state and that category and merchant identity were unchanged.
No observed ``reviewed`` boolean is invented: the stable output reports
``needs_review``, ``reviewed_at``, and ``reviewed_by_user`` as observed.

The write uses the shared retry-safe mutation executor and never inherits the
read retry policy; an uncertain transport outcome is reported as ambiguous with
a tokenized safe verification command.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any

import typer

from ..core.adapter import get_authenticated_client
from ..core.error_handler import handle_errors
from ..core.exceptions import APIError, MutationAmbiguousError, NotFoundError
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
    run_mutation_call,
    run_read_call,
)
from ..core.review_mutation import ReviewIntent, set_transaction_review_state
from ..output import emit_mutation_outcome, validate_mutation_output
from .mutation_helpers import (
    as_object as _as_object,
)
from .mutation_helpers import (
    build_preview,
)
from .mutation_helpers import (
    payload_error_details as _payload_error_details,
)
from .mutation_helpers import (
    reject_positional_targets as _reject_positional_targets,
)
from .mutation_helpers import (
    validate_transaction_id as _validate_transaction_id,
)

app = typer.Typer(
    help="Mark a transaction reviewed or return it to the review queue",
    no_args_is_help=True,
)

READ_EFFECTS: frozenset[Effect] = frozenset({Effect.READ_ONLY})
MUTATION_EFFECTS: frozenset[Effect] = frozenset({Effect.REMOTE_MUTATION})

_VERIFICATION_COMMAND = ["monarch", "transactions", "get"]
_VERIFICATION_MESSAGE = (
    "Read the transaction detail with 'monarch transactions get TRANSACTION_ID' "
    "and confirm the review state, and that category and merchant were "
    "unchanged, before retrying."
)


def _normalize_user(value: Any) -> dict[str, Any] | None:
    """Normalize the observed ``reviewedByUser`` object, or ``None``."""
    if not isinstance(value, Mapping):
        return None
    return {"id": value.get("id"), "name": value.get("name")}


def _observed_review(detail: Mapping[str, Any]) -> dict[str, Any]:
    """Report the actual observed review fields; never invent a boolean."""
    raw_needs_review = detail.get("needsReview")
    return {
        "needs_review": raw_needs_review if isinstance(raw_needs_review, bool) else None,
        "reviewed_at": detail.get("reviewedAt"),
        "reviewed_by_user": _normalize_user(detail.get("reviewedByUser")),
    }


def _identity(detail: Mapping[str, Any]) -> dict[str, Any]:
    """Capture category and merchant identity for unrelated-field integrity."""
    category = detail.get("category")
    merchant = detail.get("merchant")
    return {
        "category_id": category.get("id") if isinstance(category, Mapping) else None,
        "merchant_id": merchant.get("id") if isinstance(merchant, Mapping) else None,
        "merchant_name": merchant.get("name") if isinstance(merchant, Mapping) else None,
    }


def _read_detail(client: Any, transaction_id: str) -> Mapping[str, Any]:
    """Read one transaction detail without a pending-ID redirect.

    Enforces exact target identity: a missing transaction is a not-found error
    and a returned identity that differs from the requested one is a definitive
    refusal rather than a silent change of target. A malformed read stays on the
    structured error path.
    """
    payload = run_read_call(
        lambda: client.get_transaction_details(
            transaction_id=transaction_id, redirect_posted=False
        ),
        Operation(command="transactions review verify", effects=READ_EFFECTS),
    )
    response = _as_object(payload, "transaction detail")
    detail = response.get("getTransaction")
    if detail is None:
        raise NotFoundError(
            message="Transaction not found.",
            resource_type="transaction",
            resource_id=transaction_id,
        )
    detail = _as_object(detail, "transaction detail")
    if detail.get("id") != transaction_id:
        raise APIError(
            message=(
                "The requested transaction ID did not match the returned "
                "transaction; refusing to mutate without exact target identity."
            ),
            details={"reason": "target_identity_mismatch", "requested_id": transaction_id},
        )
    return detail


def _validate_review_response(payload: Any) -> None:
    """Validate the mutation response container.

    A definitive payload rejection raises :class:`APIError` (failed item). A
    response whose outcome cannot be established (missing or malformed
    ``errors`` field) raises :class:`MutationAmbiguousError`: the request was
    already dispatched and its remote effect is unknown. The response body is
    not used for verification; the caller performs an authoritative detail
    post-read.
    """
    response = _as_object(payload, "review mutation")
    if response.get("errors"):
        raise APIError(
            message="The review mutation was rejected by the service.",
            details={"payload_errors": _payload_error_details(response["errors"])},
        )
    container = response.get("updateTransaction")
    if not isinstance(container, Mapping):
        raise APIError(
            message="The review mutation returned no result.",
            details={"field": "updateTransaction"},
        )
    if "errors" not in container:
        raise MutationAmbiguousError(
            "The review write returned an incomplete response; remote state is unknown.",
            details={"reason": "malformed_response", "field": "updateTransaction.errors"},
        )
    errors = container["errors"]
    if errors is None:
        errors = []
    elif not isinstance(errors, list):
        raise MutationAmbiguousError(
            "The review write returned a malformed response; remote state is unknown.",
            details={"reason": "malformed_response", "field": "updateTransaction.errors"},
        )
    if errors:
        raise APIError(
            message="The review mutation was rejected by the service.",
            details={"payload_errors": _payload_error_details(errors)},
        )


def _is_no_op(observed: dict[str, Any], intent: ReviewIntent) -> bool:
    """Return whether the requested review state is already observed.

    ``needsReview=True`` means the transaction is in the review queue;
    ``needsReview=False`` means it is not. The reviewed timestamp/user are not
    used as a boolean because the upstream response provides no ``reviewed``
    field. A missing observed state never counts as a no-op.
    """
    if observed["needs_review"] is None:
        return False
    if intent is ReviewIntent.MARK_REVIEWED:
        return observed["needs_review"] is False
    return observed["needs_review"] is True


def _verification_mismatch(
    after: Mapping[str, Any], baseline: dict[str, Any], intent: ReviewIntent
) -> dict[str, Any] | None:
    """Compare the post-write detail against the intent and baseline identity."""
    observed = _observed_review(after)
    identity = _identity(after)
    mismatched_fields: list[str] = []
    expected_needs_review = intent is ReviewIntent.RETURN_TO_QUEUE
    if observed["needs_review"] != expected_needs_review:
        mismatched_fields.append("needs_review")
    for field in ("category_id", "merchant_id", "merchant_name"):
        if identity[field] != baseline[field]:
            mismatched_fields.append(field)
    if not mismatched_fields:
        return None
    return {
        "intent": intent.value,
        "mismatched_fields": mismatched_fields,
        "observed": observed,
    }


def _result(intent: ReviewIntent, observed: dict[str, Any], *, no_op: bool) -> dict[str, Any]:
    """Build the stable success/no-op result for one review intent."""
    return {
        "intent": intent.value,
        "no_op": no_op,
        "needs_review": observed["needs_review"],
        "reviewed_at": observed["reviewed_at"],
        "reviewed_by_user": observed["reviewed_by_user"],
    }


def _emit(outcome: dict[str, Any]) -> None:
    emit_mutation_outcome(outcome)


def _run_review(
    *,
    command: str,
    intent: ReviewIntent,
    transaction_id: str,
    dry_run: bool,
) -> None:
    """Execute one intent-oriented review-state operation end to end.

    Ordering is deliberate: output validation, then (for a real write)
    authorization, then client creation, then the exact-identity pre-read.
    """
    operation = Operation(command=command, effects=MUTATION_EFFECTS)
    validate_mutation_output()
    if not dry_run:
        require_mutation_authorization(operation)
    client = get_authenticated_client()
    before = _read_detail(client, transaction_id)
    observed = _observed_review(before)
    baseline = _identity(before)
    no_op = _is_no_op(observed, intent)

    if dry_run:
        _emit(
            build_preview(
                outcome_operation(command),
                transaction_id,
                {
                    "intent": intent.value,
                    "observed": observed,
                    "no_op": no_op,
                },
            )
        )
        return

    if no_op:
        _emit(
            build_mutation_outcome(
                command,
                [
                    succeeded_item(
                        "transaction", transaction_id, _result(intent, observed, no_op=True)
                    )
                ],
            )
        )
        return

    try:
        payload = run_mutation_call(
            lambda: set_transaction_review_state(client, transaction_id, intent),
            operation,
            entity_ids=(transaction_id,),
            verification=_VERIFICATION_MESSAGE,
        )
        _validate_review_response(payload)
        try:
            after = _read_detail(client, transaction_id)
        except Exception:  # noqa: BLE001 - unverified write is ambiguous
            _emit(
                build_mutation_outcome(
                    command,
                    [
                        ambiguous_item(
                            "transaction",
                            transaction_id,
                            "The review write succeeded remotely but could not be "
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
        mismatch = _verification_mismatch(after, baseline, intent)
        if mismatch is not None:
            _emit(
                build_mutation_outcome(
                    command,
                    [
                        ambiguous_item(
                            "transaction",
                            transaction_id,
                            "The review write could not be verified as requested; "
                            "remote state is unknown.",
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
                command,
                [
                    succeeded_item(
                        "transaction",
                        transaction_id,
                        _result(intent, _observed_review(after), no_op=False),
                    )
                ],
            )
        )
    except typer.Exit:
        raise
    except MutationAmbiguousError as exc:
        _emit(
            build_mutation_outcome(
                command,
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
                command,
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


@app.command("mark", context_settings={"allow_extra_args": True})
@handle_errors
@operation_effects(Effect.REMOTE_MUTATION)
def mark_reviewed(
    ctx: typer.Context,
    transaction_id: Annotated[str, typer.Option("--transaction-id", help="Transaction ID")],
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview the change without writing"),
    ] = False,
) -> None:
    """Mark one transaction reviewed (``reviewed=True``; omits ``needsReview``).

    This remote mutation requires the global --allow-mutations option, placed
    before the command path. The target is a required --transaction-id option.
    The transaction is read first to verify identity and to report a no-op when
    it is already out of the review queue. Use --dry-run to preview without
    writing.

    Examples:
        monarch --allow-mutations transactions review mark --transaction-id TXN123
        monarch transactions review mark --transaction-id TXN123 --dry-run
    """
    _reject_positional_targets(ctx.args)
    _validate_transaction_id(transaction_id)
    _run_review(
        command="transactions review mark",
        intent=ReviewIntent.MARK_REVIEWED,
        transaction_id=transaction_id,
        dry_run=dry_run,
    )


@app.command("return", context_settings={"allow_extra_args": True})
@handle_errors
@operation_effects(Effect.REMOTE_MUTATION)
def return_to_queue(
    ctx: typer.Context,
    transaction_id: Annotated[str, typer.Option("--transaction-id", help="Transaction ID")],
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview the change without writing"),
    ] = False,
) -> None:
    """Return one transaction to the review queue (``needsReview=True``).

    This remote mutation requires the global --allow-mutations option, placed
    before the command path. The target is a required --transaction-id option.
    It sends only ``needsReview=True`` and never ``reviewed=False``. The
    transaction is read first to verify identity and to report a no-op when it
    is already in the review queue. Use --dry-run to preview without writing.

    Examples:
        monarch --allow-mutations transactions review return --transaction-id TXN123
        monarch transactions review return --transaction-id TXN123 --dry-run
    """
    _reject_positional_targets(ctx.args)
    _validate_transaction_id(transaction_id)
    _run_review(
        command="transactions review return",
        intent=ReviewIntent.RETURN_TO_QUEUE,
        transaction_id=transaction_id,
        dry_run=dry_run,
    )
