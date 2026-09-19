"""Guarded transaction attachment upload (mc-2v9a).

Attaches one supported local file to one explicitly identified transaction as a
three-stage remote workflow:

1. acquire transaction-specific signed upload parameters (authenticated
   Monarch stage, state-neutral);
2. upload the file bytes to the credential-safe third-party media transport
   (prerequisite ``mc-sr92``);
3. register the uploaded asset on the transaction (authenticated Monarch stage).

Commands and services never call ``MonarchMoney.upload_attachment`` or the
upstream client's private upload methods: the authenticated stages are consumed
only through ``core.upload_transport.AttachmentUploadAdapter``. The workflow
keeps the stage boundaries so each attempted/observable state-changing stage is
an ordered effect item in the shared ``mutation-outcome.v1`` contract; an
orphaned media asset after a failed registration is reported as partial, never
rolled back or silently retried.

File validation policy (v1)
===========================

* The remote filename is the sanitized basename of ``--file``, or a validated
  ``--filename`` override. Arbitrary names and the local directory path are
  never sent to the remote service or emitted in output/diagnostics.
* Supported types are an allowlist of common receipt/document formats. The
  extension selects a canonical content type; a limited leading-bytes ("magic")
  check is applied at execution. This is local policy only: it does not
  guarantee that the remote service accepts the file.
* Maximum size is :data:`MAX_ATTACHMENT_BYTES`. Filenames are bounded by
  :data:`MAX_FILENAME_LENGTH` and reject path separators and control characters.
* Execution opens the file once with ``O_NOFOLLOW`` and validates the open
  descriptor (regular, readable, non-empty, under the size cap) before reading
  bytes from that same descriptor, so validation and upload never inspect
  different path targets. Symbolic links are refused.
* Dry-run is fully offline: it validates local metadata (existence, regular
  file, filename policy, size) without reading file contents and performs no
  authentication lookup, transaction read, signed-parameter request, or upload.
"""

from __future__ import annotations

import errno
import os
import stat
from dataclasses import dataclass
from typing import Annotated, Any

import typer

from ..core.adapter import get_authenticated_client
from ..core.async_utils import run_async
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
    resolve_invocation,
    run_mutation_call,
    run_read_async_call,
    run_read_call,
)
from ..core.upload_transport import (
    AttachmentUploadAdapter,
    MediaUploadError,
    MediaUploadResult,
)
from ..output import emit_mutation_outcome, validate_mutation_output
from .mutation_helpers import (
    build_preview,
)
from .mutation_helpers import (
    payload_error_details as _payload_error_details,
)
from .mutation_helpers import (
    validate_transaction_id as _validate_transaction_id,
)

app = typer.Typer(help="Attach supporting documents to known transactions", no_args_is_help=True)

MUTATION_EFFECTS: frozenset[Effect] = frozenset({Effect.REMOTE_MUTATION})
_READ_EFFECTS: frozenset[Effect] = frozenset({Effect.READ_ONLY})

#: Maximum accepted attachment size (10 MiB).
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
#: Maximum accepted remote filename length (characters).
MAX_FILENAME_LENGTH = 255

#: Supported extension -> (canonical content type, accepted leading bytes).
#: The magic bytes are a limited local content check, not a server guarantee.
_SUPPORTED_TYPES: dict[str, tuple[str, tuple[bytes, ...]]] = {
    ".pdf": ("application/pdf", (b"%PDF-",)),
    ".jpg": ("image/jpeg", (b"\xff\xd8\xff",)),
    ".jpeg": ("image/jpeg", (b"\xff\xd8\xff",)),
    ".png": ("image/png", (b"\x89PNG\r\n\x1a\n",)),
    ".gif": ("image/gif", (b"GIF87a", b"GIF89a")),
    ".webp": ("image/webp", (b"RIFF",)),
}

_VERIFICATION_COMMAND = ["monarch", "transactions", "get"]
_MEDIA_VERIFICATION_MESSAGE = (
    "The media upload could not be confirmed. The media host may have created "
    "an asset (which this CLI makes no attempt to clean up) and the attachment "
    "was not registered. Read the transaction detail before retrying."
)
_REGISTRATION_VERIFICATION_MESSAGE = (
    "The attachment registration could not be confirmed. Read the transaction "
    "detail to see whether the attachment was registered before retrying."
)


@dataclass(frozen=True)
class _FileMetadata:
    """Validated local file metadata and its sanitized remote name.

    Deliberately excludes the local filesystem path so it can never be emitted,
    logged, or sent to the remote service.
    """

    filename: str
    content_type: str
    extension: str
    size_bytes: int


def _resolve_remote_name(file_path: str, filename_override: str | None) -> tuple[str, str, str]:
    """Validate and return ``(remote_name, extension, content_type)``.

    The derived name is the basename of ``file_path``; an explicit override is
    validated by exactly the same policy. Path separators, control characters,
    empty/relative names, over-long names, and unsupported extensions are
    rejected without echoing the local path.
    """
    candidate = filename_override if filename_override is not None else os.path.basename(file_path)
    if not candidate or candidate in {".", ".."}:
        raise ValidationError(
            "Attachment filename must not be empty or a directory reference.",
            field="filename",
        )
    if len(candidate) > MAX_FILENAME_LENGTH:
        raise ValidationError(
            f"Attachment filename must not exceed {MAX_FILENAME_LENGTH} characters.",
            field="filename",
            details={"max_length": MAX_FILENAME_LENGTH, "length": len(candidate)},
        )
    if any(sep in candidate for sep in ("/", "\\")):
        raise ValidationError(
            "Attachment filename must not contain path separators.",
            field="filename",
        )
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in candidate):
        raise ValidationError(
            "Attachment filename must not contain control characters.",
            field="filename",
        )
    extension = os.path.splitext(candidate)[1].lower()
    supported = _SUPPORTED_TYPES.get(extension)
    if supported is None:
        raise ValidationError(
            "Unsupported attachment file type.",
            field="filename",
            details={"supported_extensions": sorted(_SUPPORTED_TYPES)},
        )
    return candidate, extension, supported[0]


def _content_matches(extension: str, head: bytes) -> bool:
    """Return whether the leading bytes match the extension's local policy."""
    patterns = _SUPPORTED_TYPES[extension][1]
    if extension == ".webp":
        return head[:4] == b"RIFF" and head[8:12] == b"WEBP"
    return any(head.startswith(pattern) for pattern in patterns)


def _check_size(size: int) -> None:
    if size == 0:
        raise ValidationError("Attachment file is empty.", field="file")
    if size > MAX_ATTACHMENT_BYTES:
        raise ValidationError(
            f"Attachment file exceeds the maximum size of {MAX_ATTACHMENT_BYTES} bytes.",
            field="file",
            details={"max_bytes": MAX_ATTACHMENT_BYTES, "size_bytes": size},
        )


def _inspect_metadata(file_path: str, filename_override: str | None) -> _FileMetadata:
    """Validate local metadata for a dry-run preview without reading contents.

    Uses ``lstat`` so a symbolic link is refused rather than followed and no
    file contents are read.
    """
    filename, extension, content_type = _resolve_remote_name(file_path, filename_override)
    try:
        info = os.lstat(file_path)
    except FileNotFoundError as exc:
        raise ValidationError("Attachment file does not exist.", field="file") from exc
    except OSError as exc:
        raise ValidationError("Attachment file could not be inspected.", field="file") from exc
    if stat.S_ISLNK(info.st_mode):
        raise ValidationError(
            "Attachment path is a symbolic link; symlinks are not supported.",
            field="file",
        )
    if not stat.S_ISREG(info.st_mode):
        raise ValidationError("Attachment path is not a regular file.", field="file")
    _check_size(info.st_size)
    return _FileMetadata(
        filename=filename,
        content_type=content_type,
        extension=extension,
        size_bytes=info.st_size,
    )


def _open_and_read(file_path: str, filename_override: str | None) -> tuple[_FileMetadata, bytes]:
    """Open the file once, validate the descriptor, and read its bytes.

    ``O_NOFOLLOW`` refuses a symbolic link at the final path component, and the
    regular/readable/size checks run on ``fstat`` of the open descriptor, so the
    bytes uploaded are exactly the bytes validated.
    """
    filename, extension, content_type = _resolve_remote_name(file_path, filename_override)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(file_path, flags)
    except FileNotFoundError as exc:
        raise ValidationError("Attachment file does not exist.", field="file") from exc
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise ValidationError(
                "Attachment path is a symbolic link; symlinks are not supported.",
                field="file",
            ) from exc
        raise ValidationError(
            "Attachment file could not be opened for reading.", field="file"
        ) from exc
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise ValidationError("Attachment path is not a regular file.", field="file")
        _check_size(info.st_size)
        content = _read_all(descriptor)
    finally:
        os.close(descriptor)
    if not _content_matches(extension, content[:12]):
        raise ValidationError(
            "Attachment file content does not match its extension.",
            field="file",
        )
    return (
        _FileMetadata(
            filename=filename,
            content_type=content_type,
            extension=extension,
            size_bytes=len(content),
        ),
        content,
    )


def _read_all(descriptor: int) -> bytes:
    """Read the whole descriptor in bounded chunks (size already validated)."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = os.read(descriptor, 65536)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_ATTACHMENT_BYTES:
            raise ValidationError(
                f"Attachment file exceeds the maximum size of {MAX_ATTACHMENT_BYTES} bytes.",
                field="file",
                details={"max_bytes": MAX_ATTACHMENT_BYTES},
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _read_transaction_detail(client: Any, transaction_id: str) -> Any:
    """Read one transaction detail without a pending-ID redirect.

    Returns the raw ``getTransaction`` container (which may be ``None`` for a
    missing transaction or a non-object for a malformed detail). A malformed
    outer payload and any read failure raise on the structured error path.
    """
    payload = run_read_call(
        lambda: client.get_transaction_details(
            transaction_id=transaction_id, redirect_posted=False
        ),
        Operation(command="transactions attachments add verify", effects=_READ_EFFECTS),
    )
    if not isinstance(payload, dict):
        raise APIError(
            message="The transaction detail response was not in the expected shape.",
            details={"stage": "verify_target"},
        )
    return payload.get("getTransaction")


def _require_exact_target(client: Any, transaction_id: str) -> None:
    """Verify the exact transaction exists before any upload.

    The read does not redirect a pending identifier, and a returned identity
    that differs from the requested one is a definitive refusal rather than a
    silent change of target.
    """
    detail = _read_transaction_detail(client, transaction_id)
    if detail is None:
        raise NotFoundError(
            message="Transaction not found.",
            resource_type="transaction",
            resource_id=transaction_id,
        )
    if not isinstance(detail, dict):
        raise APIError(
            message="The transaction detail response was not in the expected shape.",
            details={"stage": "verify_target"},
        )
    returned = detail.get("id")
    if returned != transaction_id:
        raise APIError(
            message=(
                "The requested transaction ID did not match the returned "
                "transaction; refusing to upload without exact target identity."
            ),
            details={"stage": "verify_target", "requested_id": transaction_id},
        )


def _attachment_identity(attachment: dict[str, Any]) -> tuple[str | None, str | None]:
    """Return ``(attachment_id, public_id)`` when each is a non-empty string."""
    raw_id = attachment.get("id")
    raw_public = attachment.get("publicId")
    attachment_id = raw_id if isinstance(raw_id, str) and raw_id else None
    public_id = raw_public if isinstance(raw_public, str) and raw_public else None
    return attachment_id, public_id


def _confirm_registration(
    client: Any,
    transaction_id: str,
    attachment_id: str | None,
    public_id: str | None,
) -> bool:
    """Confirm the returned attachment identity appears in the transaction.

    Reads the transaction detail (strict, no redirect) and matches the
    registration identity by ``id`` then ``publicId``. A read failure returns
    ``False`` so the caller reports an unverified ambiguity rather than a false
    success.
    """
    try:
        detail = _read_transaction_detail(client, transaction_id)
    except Exception:  # noqa: BLE001 - unverified registration is ambiguous
        return False
    if not isinstance(detail, dict):
        return False
    attachments = detail.get("attachments")
    if not isinstance(attachments, list):
        return False
    for item in attachments:
        if not isinstance(item, dict):
            continue
        item_id, item_public = _attachment_identity(item)
        if attachment_id is not None and item_id == attachment_id:
            return True
        if public_id is not None and item_public == public_id:
            return True
    return False


def _media_succeeded_item(media: MediaUploadResult, metadata: _FileMetadata) -> dict[str, Any]:
    return succeeded_item(
        "attachment_media",
        media.public_id,
        {
            "public_id": media.public_id,
            "extension": media.extension,
            "size_bytes": media.size_bytes,
            "filename": metadata.filename,
        },
    )


def _emit(outcome: dict[str, Any]) -> None:
    emit_mutation_outcome(outcome)


@app.command("add", context_settings={"allow_extra_args": True})
@handle_errors
@operation_effects(Effect.REMOTE_MUTATION)
def add_attachment(
    ctx: typer.Context,
    transaction_id: Annotated[
        str, typer.Option("--transaction-id", help="Transaction ID to attach the file to")
    ],
    file: Annotated[str, typer.Option("--file", help="Path to the local file to attach")],
    filename: Annotated[
        str | None,
        typer.Option(
            "--filename",
            help="Remote filename override (validated by the same policy as the derived basename)",
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Validate local metadata offline and preview without any network call",
        ),
    ] = False,
) -> None:
    """Attach one supported local file to an explicitly identified transaction.

    A three-stage remote workflow: acquire signed upload parameters, upload the
    file to the credential-safe media transport, then register the attachment.
    The target uses a required ``--transaction-id`` option and the file uses a
    ``--file`` option; there are no positional arguments. The local directory
    path and file contents are never emitted.

    This remote mutation requires the global --allow-mutations option, placed
    before the command path (for example:
    monarch --allow-mutations transactions attachments add \\
        --transaction-id TXN123 --file ./receipt.pdf).

    ``--dry-run`` is a fully offline preview: it validates local metadata only
    and performs no authentication lookup, transaction read, signed-parameter
    request, or upload. It never requires --allow-mutations.

    Examples:
        monarch transactions attachments add \\
            --transaction-id TXN123 --file ./receipt.pdf --dry-run
        monarch --allow-mutations transactions attachments add \\
            --transaction-id TXN123 --file ./receipt.pdf
        monarch --allow-mutations transactions attachments add \\
            --transaction-id TXN123 --file /tmp/scan.png --filename "receipt.png"
    """
    if ctx.args:
        raise ValidationError(
            "Unexpected positional arguments; use --transaction-id and --file.",
            field="arguments",
        )
    _validate_transaction_id(transaction_id)
    operation = resolve_invocation(
        "transactions attachments add", MUTATION_EFFECTS, dry_run=dry_run
    )
    validate_mutation_output()

    if dry_run:
        metadata = _inspect_metadata(file, filename)
        _emit(
            build_preview(
                outcome_operation(operation.command),
                transaction_id,
                {
                    "transaction_id": transaction_id,
                    "filename": metadata.filename,
                    "size_bytes": metadata.size_bytes,
                    "content_type": metadata.content_type,
                },
            )
        )
        return

    require_mutation_authorization(operation)
    # File validation precedes authentication and any remote operation.
    metadata, content = _open_and_read(file, filename)

    client = get_authenticated_client()
    _require_exact_target(client, transaction_id)
    adapter = AttachmentUploadAdapter(client)

    # Stage 1: acquire signed parameters. State-neutral and retry-safe, so it
    # uses the read executor's timeout/retry policy. A failure here happens
    # before any mutation and keeps the structured error contract.
    params = run_async(
        run_read_async_call(
            lambda: adapter.acquire_upload_params(transaction_id),
            Operation(command="transactions attachments add acquire", effects=_READ_EFFECTS),
        )
    )

    # Stage 2: media upload (one attempt; ambiguity is honest, never retried).
    try:
        media = run_mutation_call(
            lambda: adapter.upload_media(params, content, metadata.filename),
            operation,
            entity_ids=(transaction_id,),
            verification=_MEDIA_VERIFICATION_MESSAGE,
        )
    except MediaUploadError as exc:
        error = error_from_exception(exc)
        _emit(
            build_mutation_outcome(
                operation.command,
                [
                    failed_item(
                        "attachment_media",
                        metadata.filename,
                        error["code"],
                        error["message"],
                        error["details"],
                    )
                ],
            )
        )
        return
    except MutationAmbiguousError as exc:
        _emit(
            build_mutation_outcome(
                operation.command,
                [
                    ambiguous_item(
                        "attachment_media",
                        metadata.filename,
                        exc.message,
                        {"remote_state": "unknown", "reason": exc.details.get("reason")},
                    )
                ],
                verification=verification_object(
                    _MEDIA_VERIFICATION_MESSAGE,
                    command=[*_VERIFICATION_COMMAND, transaction_id],
                ),
            )
        )
        return

    media_item = _media_succeeded_item(media, metadata)

    # Stage 3: register the uploaded asset (one attempt).
    try:
        registration = run_mutation_call(
            lambda: adapter.register_attachment(
                transaction_id=transaction_id,
                filename=metadata.filename,
                media=media,
            ),
            operation,
            entity_ids=(transaction_id,),
            verification=_REGISTRATION_VERIFICATION_MESSAGE,
        )
    except MutationAmbiguousError as exc:
        _emit(
            build_mutation_outcome(
                operation.command,
                [
                    media_item,
                    ambiguous_item(
                        "attachment",
                        metadata.filename,
                        exc.message,
                        {"remote_state": "unknown", "reason": exc.details.get("reason")},
                    ),
                ],
                verification=verification_object(
                    _REGISTRATION_VERIFICATION_MESSAGE,
                    command=[*_VERIFICATION_COMMAND, transaction_id],
                ),
            )
        )
        return
    except Exception as exc:  # noqa: BLE001 - classified by the contract
        error = error_from_exception(exc)
        _emit(
            build_mutation_outcome(
                operation.command,
                [
                    media_item,
                    failed_item(
                        "attachment",
                        metadata.filename,
                        error["code"],
                        error["message"],
                        error["details"],
                    ),
                ],
            )
        )
        return

    if registration.errors:
        _emit(
            build_mutation_outcome(
                operation.command,
                [
                    media_item,
                    failed_item(
                        "attachment",
                        metadata.filename,
                        "API_ERROR",
                        "The attachment registration was rejected by the service.",
                        {
                            "stage": "register_attachment",
                            "payload_errors": _payload_error_details(list(registration.errors)),
                        },
                    ),
                ],
            )
        )
        return

    attachment = registration.attachment or {}
    attachment_id, public_id = _attachment_identity(attachment)
    best_known_id = attachment_id or public_id or metadata.filename
    if attachment_id is None and public_id is None:
        _emit(
            build_mutation_outcome(
                operation.command,
                [
                    media_item,
                    ambiguous_item(
                        "attachment",
                        best_known_id,
                        "The attachment registration returned no usable attachment "
                        "identity; the attachment may exist. Remote state is unknown.",
                        {"remote_state": "unknown", "reason": "missing_identity"},
                    ),
                ],
                verification=verification_object(
                    _REGISTRATION_VERIFICATION_MESSAGE,
                    command=[*_VERIFICATION_COMMAND, transaction_id],
                ),
            )
        )
        return

    if not _confirm_registration(client, transaction_id, attachment_id, public_id):
        _emit(
            build_mutation_outcome(
                operation.command,
                [
                    media_item,
                    ambiguous_item(
                        "attachment",
                        best_known_id,
                        "The registered attachment could not be confirmed in the "
                        "transaction detail; remote state is unknown.",
                        {"remote_state": "unknown", "reason": "verification_mismatch"},
                    ),
                ],
                verification=verification_object(
                    _REGISTRATION_VERIFICATION_MESSAGE,
                    command=[*_VERIFICATION_COMMAND, transaction_id],
                ),
            )
        )
        return

    server_extension = attachment.get("extension")
    server_size = attachment.get("sizeBytes")
    _emit(
        build_mutation_outcome(
            operation.command,
            [
                media_item,
                succeeded_item(
                    "attachment",
                    best_known_id,
                    {
                        "transaction_id": transaction_id,
                        "attachment_id": attachment_id,
                        "public_id": public_id,
                        "filename": metadata.filename,
                        "extension": (
                            server_extension
                            if isinstance(server_extension, str)
                            else media.extension
                        ),
                        "size_bytes": (
                            server_size
                            if isinstance(server_size, int) and not isinstance(server_size, bool)
                            else media.size_bytes
                        ),
                    },
                ),
            ],
        )
    )


__all__ = ["app"]
