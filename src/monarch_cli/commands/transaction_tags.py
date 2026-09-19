"""Read-only and guarded transaction tag workflows."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Annotated, Any

import typer

from ..core.adapter import get_authenticated_client
from ..core.error_handler import handle_errors
from ..core.exceptions import APIError, MutationAmbiguousError, NotFoundError, ValidationError
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
from ..output import OutputFormat, emit_mutation_outcome, output, validate_mutation_output
from .mutation_helpers import (
    as_object as _as_object,
)
from .mutation_helpers import (
    build_preview,
    confirm_destructive,
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

app = typer.Typer(help="Discover and safely assign transaction tags", no_args_is_help=True)

READ_EFFECTS: frozenset[Effect] = frozenset({Effect.READ_ONLY})
MUTATION_EFFECTS: frozenset[Effect] = frozenset({Effect.REMOTE_MUTATION})
_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")

_TAG_VERIFICATION_COMMAND = ["monarch", "transactions", "tags", "show"]


def _normal_tag(value: Any) -> dict[str, Any]:
    tag = _as_object(value, "transaction tag")
    return {
        "id": tag.get("id"),
        "name": tag.get("name"),
        "color": tag.get("color"),
        "order": tag.get("order"),
        "transaction_count": tag.get("transactionCount"),
    }


def _tag_list(payload: Any) -> list[dict[str, Any]]:
    response = _as_object(payload, "transaction tags")
    tags = response.get("householdTransactionTags")
    if tags is None:
        # A few client/test adapters return the collection directly under tags.
        tags = response.get("tags")
    if not isinstance(tags, list):
        raise APIError(
            message="Malformed transaction tags response.",
            details={"field": "householdTransactionTags", "expected": "array"},
        )
    return [_normal_tag(tag) for tag in tags]


def _mutation_container(payload: Any, key: str) -> Mapping[str, Any]:
    response = _as_object(payload, "mutation")
    if response.get("errors"):
        raise APIError(
            message="The tag mutation was rejected by the service.",
            details={"payload_errors": _payload_error_details(response["errors"])},
        )
    container = response.get(key)
    if not isinstance(container, Mapping):
        raise APIError(
            message="The tag mutation returned no result.",
            details={"field": key},
        )
    if container.get("errors"):
        raise APIError(
            message="The tag mutation was rejected by the service.",
            details={"payload_errors": _payload_error_details(container["errors"])},
        )
    return container


def _transaction_detail(payload: Any, transaction_id: str) -> Mapping[str, Any]:
    response = _as_object(payload, "transaction detail")
    detail = response.get("getTransaction")
    if detail is None:
        raise NotFoundError(
            message="Transaction not found.",
            resource_type="transaction",
            resource_id=transaction_id,
        )
    return _as_object(detail, "transaction detail")


def _tag_ids(detail: Mapping[str, Any]) -> list[str]:
    tags = detail.get("tags")
    if not isinstance(tags, list):
        raise APIError(
            message="Malformed transaction tag assignment response.", details={"field": "tags"}
        )
    result: list[str] = []
    for index, tag in enumerate(tags):
        if not isinstance(tag, Mapping) or not isinstance(tag.get("id"), str):
            raise APIError(
                message="Malformed transaction tag assignment response.",
                details={"field": "tags", "index": index},
            )
        result.append(tag["id"])
    return result


def _dedupe(ids: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in ids:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _emit(outcome: dict[str, Any]) -> None:
    emit_mutation_outcome(outcome)


@app.command("list")
@handle_errors
@operation_effects(Effect.READ_ONLY)
def list_tags(
    format: Annotated[OutputFormat | None, typer.Option("-f", "--format")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
    raw: Annotated[bool, typer.Option("--raw")] = False,
) -> None:
    """List all available transaction tags (read-only)."""
    client = get_authenticated_client()
    payload = run_read_call(
        lambda: client.get_transaction_tags(),
        Operation(command="transactions tags list", effects=READ_EFFECTS),
    )
    data = payload if raw else _tag_list(payload)
    output(data, OutputFormat.JSON if json_output else format)


@app.command("show")
@handle_errors
@operation_effects(Effect.READ_ONLY)
def show_tags(
    transaction_id: Annotated[str, typer.Argument(help="Transaction ID")],
    format: Annotated[OutputFormat | None, typer.Option("-f", "--format")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
    raw: Annotated[bool, typer.Option("--raw")] = False,
) -> None:
    """Show tags assigned to one transaction (read-only)."""
    _validate_transaction_id(transaction_id)
    client = get_authenticated_client()
    payload = run_read_call(
        lambda: client.get_transaction_details(transaction_id=transaction_id, redirect_posted=True),
        Operation(command="transactions tags show", effects=READ_EFFECTS),
    )
    if raw:
        data: Any = payload
    else:
        detail = _transaction_detail(payload, transaction_id)
        _tag_ids(detail)
        tags = detail["tags"]
        data = {
            "transaction_id": transaction_id,
            "returned_transaction_id": detail.get("id"),
            "tags": [_normal_tag(tag) for tag in tags],
        }
    output(data, OutputFormat.JSON if json_output else format)


@app.command("create")
@handle_errors
@operation_effects(Effect.REMOTE_MUTATION)
def create_tag(
    name: Annotated[str | None, typer.Option("--name")] = None,
    color: Annotated[str | None, typer.Option("--color")] = None,
) -> None:
    """Create a reusable transaction tag.

    This remote mutation requires the global --allow-mutations option, placed
    before the command path (for example:
    monarch --allow-mutations transactions tags create --name Work --color '#112233').
    Both --name and a six-digit --color are required.
    """
    if name is None or not name.strip():
        raise ValidationError("Tag name must be non-empty after trimming.", field="name")
    if color is None or not _COLOR_RE.fullmatch(color):
        raise ValidationError("Color must match #[0-9A-Fa-f]{6}.", field="color")
    operation = Operation(command="transactions tags create", effects=MUTATION_EFFECTS)
    validate_mutation_output()
    require_mutation_authorization(operation)
    client = get_authenticated_client()
    try:
        payload = run_mutation_call(
            lambda: client.create_transaction_tag(name=name.strip(), color=color), operation
        )
        container = _mutation_container(payload, "createTransactionTag")
        tag = container.get("tag")
        if not isinstance(tag, Mapping) or not isinstance(tag.get("id"), str):
            raise APIError(message="The tag creation response did not include a tag ID.")
        _emit(
            build_mutation_outcome(
                operation.command, [succeeded_item("tag", tag["id"], {"tag": _normal_tag(tag)})]
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
                        "tag",
                        "unknown",
                        exc.message,
                        {"remote_state": "unknown", "reason": exc.details.get("reason")},
                    )
                ],
                verification=verification_object(
                    "Verify whether the tag was created before retrying.",
                    command=["monarch", "transactions", "tags", "list"],
                ),
            )
        )
    except Exception as exc:
        error = error_from_exception(exc)
        _emit(
            build_mutation_outcome(
                operation.command,
                [failed_item("tag", "unknown", error["code"], error["message"], error["details"])],
            )
        )


def _fetch_known_tags(client: Any) -> list[dict[str, Any]]:
    """Fetch the household tag collection once for resolution/validation."""
    return _tag_list(
        run_read_call(
            lambda: client.get_transaction_tags(),
            Operation(command="transactions tags list", effects=READ_EFFECTS),
        )
    )


def _resolve_tag_refs(
    known: list[dict[str, Any]],
    tag_ids: list[str],
    tag_names: list[str],
) -> list[str]:
    """Resolve and validate mixed ``--tag-id`` / ``--tag-name`` references.

    Names match exactly and case-sensitively, with CLI-input-only whitespace
    trimming; upstream names are never normalized. Unknown names/IDs and
    duplicate-name ambiguities are pre-mutation validation errors. Resolved IDs
    are deduplicated in first-seen order.
    """
    known_ids = {tag["id"] for tag in known if isinstance(tag.get("id"), str)}
    resolved: list[str] = []
    unknown_ids: list[str] = []
    for raw in tag_ids:
        tag_id = raw.strip()
        if tag_id in known_ids:
            resolved.append(tag_id)
        else:
            unknown_ids.append(tag_id)
    if unknown_ids:
        raise ValidationError(
            "Unknown transaction tag ID(s).",
            field="tag_ids",
            details={"unknown_ids": unknown_ids},
        )

    unknown_names: list[str] = []
    ambiguous: dict[str, list[str]] = {}
    for raw in tag_names:
        name = raw.strip()
        matches = [
            tag["id"] for tag in known if tag.get("name") == name and isinstance(tag.get("id"), str)
        ]
        if not matches:
            unknown_names.append(name)
        elif len(matches) > 1:
            ambiguous[name] = matches
        else:
            resolved.append(matches[0])
    if unknown_names:
        raise ValidationError(
            "Unknown transaction tag name(s).",
            field="tag_names",
            details={"unknown_names": unknown_names},
        )
    if ambiguous:
        raise ValidationError(
            "Ambiguous transaction tag name(s): multiple tags share the name.",
            field="tag_names",
            details={"ambiguous_names": ambiguous},
        )
    return _dedupe(resolved)


def _read_current_tags(client: Any, transaction_id: str) -> list[str]:
    detail = _transaction_detail(
        run_read_call(
            lambda: client.get_transaction_details(
                transaction_id=transaction_id, redirect_posted=True
            ),
            Operation(command="transactions tags show", effects=READ_EFFECTS),
        ),
        transaction_id,
    )
    return _tag_ids(detail)


def _require_tag_refs(tag_id: list[str] | None, tag_name: list[str] | None) -> None:
    if not tag_id and not tag_name:
        raise ValidationError("At least one --tag-id or --tag-name is required.", field="tag_ids")


def _write_tag_set(
    client: Any,
    transaction_id: str,
    final_ids: list[str],
    operation: Operation,
    *,
    confirmation_message: str | None,
    result: dict[str, Any],
) -> None:
    """Confirm, write the full tag set once, verify it, and emit the outcome.

    ``add`` is a read-modify-write over the full-set endpoint: it is not atomic
    against concurrent tag changes because the upstream API has no add
    endpoint. A verified response whose tag set differs from ``final_ids`` is
    reported as a verification-mismatch ambiguous outcome, never silently
    repaired.
    """
    if confirmation_message is not None:
        confirm_destructive(confirmation_message, operation=operation.command)
    try:
        payload = run_mutation_call(
            lambda: client.set_transaction_tags(transaction_id=transaction_id, tag_ids=final_ids),
            operation,
            entity_ids=(transaction_id,),
            verification=(
                "Inspect the transaction's tags with 'monarch transactions tags show "
                "TRANSACTION_ID' before retrying."
            ),
        )
        container = _mutation_container(payload, "setTransactionTags")
        tx = container.get("transaction")
        if not isinstance(tx, Mapping):
            raise APIError(message="The tag write response did not include the transaction.")
        observed = _tag_ids(tx)
        if set(observed) != set(final_ids):
            _emit(
                build_mutation_outcome(
                    operation.command,
                    [
                        ambiguous_item(
                            "transaction",
                            transaction_id,
                            "The tag write returned a tag set different from the "
                            "final set; remote state is unknown.",
                            {
                                "reason": "verification_mismatch",
                                "expected_tag_ids": final_ids,
                                "observed_tag_ids": observed,
                                "remote_state": "unknown",
                            },
                        )
                    ],
                    verification=verification_object(
                        "Inspect the transaction's tags and confirm the applied "
                        "set before retrying.",
                        command=[*_TAG_VERIFICATION_COMMAND, transaction_id],
                    ),
                )
            )
            return
        _emit(
            build_mutation_outcome(
                operation.command,
                [succeeded_item("transaction", transaction_id, result)],
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
                    "Inspect the transaction's tags and confirm the applied set before retrying.",
                    command=[*_TAG_VERIFICATION_COMMAND, transaction_id],
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


def _start_tag_mutation(command: str, *, dry_run: bool = False) -> tuple[Operation, Any]:
    """Validate output, optionally authorize, and return operation + client.

    A dry-run preview performs read-only work only: it never requires
    ``--allow-mutations`` and never prompts for confirmation.
    """
    operation = Operation(command=command, effects=MUTATION_EFFECTS)
    validate_mutation_output()
    if not dry_run:
        require_mutation_authorization(operation)
    return operation, get_authenticated_client()


def _emit_tag_preview(
    operation: Operation,
    transaction_id: str,
    detail: dict[str, Any],
) -> None:
    emit_mutation_outcome(
        build_preview(outcome_operation(operation.command), transaction_id, detail)
    )


@app.command("replace", context_settings={"allow_extra_args": True})
@handle_errors
@operation_effects(Effect.REMOTE_MUTATION)
def replace_tags(
    ctx: typer.Context,
    transaction_id: Annotated[str, typer.Option("--transaction-id", help="Transaction ID")],
    tag_id: Annotated[
        list[str] | None,
        typer.Option("--tag-id", help="Known tag ID (repeatable)"),
    ] = None,
    tag_name: Annotated[
        list[str] | None,
        typer.Option("--tag-name", help="Exact tag name (repeatable)"),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview the resolved tag set without writing"),
    ] = False,
) -> None:
    """Replace the complete tag set for one transaction.

    This remote mutation requires the global --allow-mutations option, placed
    before the command path. Destructive: prompts unless --yes is given after
    --allow-mutations. Use --dry-run to preview the resolved set without
    writing.

    Examples:
        monarch --allow-mutations transactions tags replace \\
            --transaction-id TXN123 --tag-id TAG1 --tag-name "Travel"
        monarch transactions tags replace --transaction-id TXN123 --tag-id TAG1 --dry-run
    """
    _reject_positional_targets(ctx.args)
    _validate_transaction_id(transaction_id)
    _require_tag_refs(tag_id, tag_name)
    operation, client = _start_tag_mutation("transactions tags replace", dry_run=dry_run)
    known = _fetch_known_tags(client)
    requested = _resolve_tag_refs(known, tag_id or [], tag_name or [])
    current = _read_current_tags(client, transaction_id)
    if dry_run:
        _emit_tag_preview(
            operation,
            transaction_id,
            {
                "requested_tag_ids": requested,
                "current_tag_ids": current,
                "final_tag_ids": requested,
                "added_tag_ids": [t for t in requested if t not in set(current)],
                "removed_tag_ids": [t for t in current if t not in set(requested)],
                "no_op": set(current) == set(requested),
            },
        )
        return
    if set(current) == set(requested):
        _emit(
            build_mutation_outcome(
                operation.command,
                [
                    succeeded_item(
                        "transaction", transaction_id, {"tag_ids": requested, "no_op": True}
                    )
                ],
            )
        )
        return
    _write_tag_set(
        client,
        transaction_id,
        requested,
        operation,
        confirmation_message=(
            f"Replace all tags on transaction {transaction_id} with {requested!r}?"
        ),
        result={"tag_ids": requested, "no_op": False},
    )


@app.command("add", context_settings={"allow_extra_args": True})
@handle_errors
@operation_effects(Effect.REMOTE_MUTATION)
def add_tags(
    ctx: typer.Context,
    transaction_id: Annotated[str, typer.Option("--transaction-id", help="Transaction ID")],
    tag_id: Annotated[
        list[str] | None,
        typer.Option("--tag-id", help="Known tag ID (repeatable)"),
    ] = None,
    tag_name: Annotated[
        list[str] | None,
        typer.Option("--tag-name", help="Exact tag name (repeatable)"),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview the additive result without writing"),
    ] = False,
) -> None:
    """Add tags to a transaction, preserving its existing tags.

    This remote mutation requires the global --allow-mutations option, placed
    before the command path. Read-modify-write over the full-set endpoint; not
    atomic against concurrent tag changes. Already-present tags are skipped; an
    already-satisfied request is a deterministic no-op. Existing tags not
    present in household discovery are preserved verbatim. Use --dry-run to
    preview the additive result without writing.

    Examples:
        monarch --allow-mutations transactions tags add \\
            --transaction-id TXN123 --tag-name "Travel"
        monarch transactions tags add --transaction-id TXN123 --tag-name "Travel" --dry-run
    """
    _reject_positional_targets(ctx.args)
    _validate_transaction_id(transaction_id)
    _require_tag_refs(tag_id, tag_name)
    operation, client = _start_tag_mutation("transactions tags add", dry_run=dry_run)
    known = _fetch_known_tags(client)
    requested = _resolve_tag_refs(known, tag_id or [], tag_name or [])
    current = _read_current_tags(client, transaction_id)
    current_set = set(current)
    added = [tag for tag in requested if tag not in current_set]
    skipped = [tag for tag in requested if tag in current_set]
    final = _dedupe([*current, *added])
    if dry_run:
        _emit_tag_preview(
            operation,
            transaction_id,
            {
                "requested_tag_ids": requested,
                "current_tag_ids": current,
                "final_tag_ids": final,
                "added_tag_ids": added,
                "already_present_tag_ids": skipped,
                "no_op": not added,
            },
        )
        return
    if not added:
        _emit(
            build_mutation_outcome(
                operation.command,
                [
                    succeeded_item(
                        "transaction",
                        transaction_id,
                        {
                            "tag_ids": current,
                            "added_tag_ids": [],
                            "skipped_tag_ids": skipped,
                            "no_op": True,
                        },
                    )
                ],
            )
        )
        return
    _write_tag_set(
        client,
        transaction_id,
        final,
        operation,
        confirmation_message=None,
        result={
            "tag_ids": final,
            "added_tag_ids": added,
            "skipped_tag_ids": skipped,
            "no_op": False,
        },
    )


@app.command("clear", context_settings={"allow_extra_args": True})
@handle_errors
@operation_effects(Effect.REMOTE_MUTATION)
def clear_tags(
    ctx: typer.Context,
    transaction_id: Annotated[str, typer.Option("--transaction-id", help="Transaction ID")],
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview the clear without writing"),
    ] = False,
) -> None:
    """Explicitly clear every tag from one transaction.

    This remote mutation requires the global --allow-mutations option, placed
    before the command path. Destructive: prompts unless --yes is given after
    --allow-mutations. Use --dry-run to preview the clear without writing.
    """
    _reject_positional_targets(ctx.args)
    _validate_transaction_id(transaction_id)
    operation, client = _start_tag_mutation("transactions tags clear", dry_run=dry_run)
    current = _read_current_tags(client, transaction_id)
    if dry_run:
        _emit_tag_preview(
            operation,
            transaction_id,
            {
                "current_tag_ids": current,
                "final_tag_ids": [],
                "removed_tag_ids": current,
                "no_op": not current,
            },
        )
        return
    if not current:
        _emit(
            build_mutation_outcome(
                operation.command,
                [succeeded_item("transaction", transaction_id, {"tag_ids": [], "no_op": True})],
            )
        )
        return
    _write_tag_set(
        client,
        transaction_id,
        [],
        operation,
        confirmation_message=f"Clear all tags on transaction {transaction_id}?",
        result={"tag_ids": [], "no_op": False},
    )
