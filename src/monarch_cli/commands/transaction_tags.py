"""Read-only and guarded transaction tag workflows."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Annotated, Any

import typer

from ..core.adapter import get_authenticated_client
from ..core.config import get_config
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
from ..core.prompting import confirm_action
from ..output import OutputFormat, emit_mutation_outcome, output, validate_mutation_output

app = typer.Typer(help="Discover and safely assign transaction tags", no_args_is_help=True)

READ_EFFECTS: frozenset[Effect] = frozenset({Effect.READ_ONLY})
MUTATION_EFFECTS: frozenset[Effect] = frozenset({Effect.REMOTE_MUTATION})
_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")

_TAG_VERIFICATION_COMMAND = ["monarch", "transactions", "tags", "show"]


def _as_object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise APIError(
            message=f"Malformed {label} response.",
            details={"expected": "object", "received": type(value).__name__},
        )
    return value


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


def _payload_error_details(errors: Any) -> list[dict[str, Any]]:
    if not isinstance(errors, list):
        return [{"message": "The service returned an invalid error payload."}]
    result: list[dict[str, Any]] = []
    for error in errors:
        if not isinstance(error, Mapping):
            result.append({"message": "The service returned an invalid error payload."})
            continue
        item: dict[str, Any] = {}
        for key in ("message", "code", "field"):
            if isinstance(error.get(key), str):
                item[key] = error[key]
        field_errors = error.get("fieldErrors")
        if isinstance(field_errors, list):
            item["field_errors"] = [
                {
                    key: entry[key]
                    for key in ("field", "messages")
                    if isinstance(entry, Mapping) and key in entry
                }
                for entry in field_errors
                if isinstance(entry, Mapping)
            ]
        result.append(item or {"message": "The service rejected the request."})
    return result


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


def _validate_transaction_id(transaction_id: str) -> None:
    if not transaction_id.strip():
        raise ValidationError("Transaction ID must not be empty.", field="transaction_id")


def _emit(outcome: dict[str, Any]) -> None:
    emit_mutation_outcome(outcome)


def _confirm(operation: str, transaction_id: str, tag_ids: list[str]) -> None:
    config = get_config()
    if not config.confirm_destructive:
        return
    if not confirm_action(
        f"Replace all tags on transaction {transaction_id} with {tag_ids!r}?",
        missing_input="destructive confirmation",
        remedy="pass --yes (after --allow-mutations) or disable confirm_destructive",
        operation=operation,
    ):
        raise ValidationError("Mutation was not confirmed.", field="confirmation")


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
    """Create a reusable transaction tag."""
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


def _set_tags(transaction_id: str, requested: list[str], operation_name: str) -> None:
    operation = Operation(command=operation_name, effects=MUTATION_EFFECTS)
    validate_mutation_output()
    require_mutation_authorization(operation)
    client = get_authenticated_client()
    # Discovery is read-only and deliberately precedes confirmation/mutation.
    known = _tag_list(
        run_read_call(
            lambda: client.get_transaction_tags(),
            Operation(command="transactions tags list", effects=READ_EFFECTS),
        )
    )
    known_ids = {tag["id"] for tag in known if isinstance(tag.get("id"), str)}
    unknown = [tag_id for tag_id in requested if tag_id not in known_ids]
    if unknown:
        raise ValidationError(
            "Unknown transaction tag ID(s).",
            field="tag_ids",
            details={"unknown_ids": unknown},
        )
    detail = _transaction_detail(
        run_read_call(
            lambda: client.get_transaction_details(
                transaction_id=transaction_id, redirect_posted=True
            ),
            Operation(command="transactions tags show", effects=READ_EFFECTS),
        ),
        transaction_id,
    )
    current = _tag_ids(detail)
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
    _confirm(operation_name, transaction_id, requested)
    try:
        payload = run_mutation_call(
            lambda: client.set_transaction_tags(transaction_id=transaction_id, tag_ids=requested),
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
            raise APIError(message="The tag replacement response did not include the transaction.")
        observed = _tag_ids(tx)
        if set(observed) != set(requested):
            _emit(
                build_mutation_outcome(
                    operation.command,
                    [
                        ambiguous_item(
                            "transaction",
                            transaction_id,
                            "The tag write returned a tag set different from the "
                            "requested set; remote state is unknown.",
                            {
                                "reason": "verification_mismatch",
                                "expected_tag_ids": requested,
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
                [
                    succeeded_item(
                        "transaction", transaction_id, {"tag_ids": requested, "no_op": False}
                    )
                ],
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


@app.command("replace")
@handle_errors
@operation_effects(Effect.REMOTE_MUTATION)
def replace_tags(
    transaction_id: Annotated[str, typer.Argument(help="Transaction ID")],
    tag_ids: Annotated[list[str], typer.Argument(help="One or more known tag IDs")],
) -> None:
    """Replace the complete tag set for one transaction."""
    _validate_transaction_id(transaction_id)
    requested = _dedupe(tag_ids)
    if not requested:
        raise ValidationError("Replacement requires at least one tag ID.", field="tag_ids")
    _set_tags(transaction_id, requested, "transactions tags replace")


@app.command("clear")
@handle_errors
@operation_effects(Effect.REMOTE_MUTATION)
def clear_tags(
    transaction_id: Annotated[str, typer.Argument(help="Transaction ID")],
) -> None:
    """Explicitly clear every tag from one transaction."""
    _validate_transaction_id(transaction_id)
    _set_tags(transaction_id, [], "transactions tags clear")
