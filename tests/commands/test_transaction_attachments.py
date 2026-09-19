"""Contract tests for the guarded transaction attachment upload (mc-2v9a).

These tests mock the file, transaction-read, upload, and registration
boundaries. They assert authorization, the offline dry-run, descriptor
validation, exact target verification, every stage outcome, post-success
verification, repeat-upload behavior, and output privacy. No live financial API
call is made by the default suite.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from jsonschema import Draft202012Validator
from typer.testing import CliRunner

from monarch_cli.commands import transaction_attachments as module
from monarch_cli.commands.transactions import app as transactions_app
from monarch_cli.core.config import Config, reset_config, set_config
from monarch_cli.core.exceptions import APIError, MutationAmbiguousError
from monarch_cli.core.operations import reset_mutation_authorization, set_mutation_authorized
from monarch_cli.core.upload_transport import (
    AttachmentRegistration,
    MediaUploadError,
    MediaUploadResult,
)
from monarch_cli.core.upload_transport import (
    AttachmentUploadAdapter as RealAdapter,
)
from monarch_cli.schemas import load_schema

runner = CliRunner()

_PDF_BYTES = b"%PDF-1.4\n% test pdf content\n"
_MUTATION_OUTCOME_VALIDATOR = Draft202012Validator(load_schema("mutation-outcome"))


@pytest.fixture(autouse=True)
def policy() -> None:
    set_mutation_authorized(True)
    set_config(Config(confirm_destructive=False))
    yield
    reset_mutation_authorization()
    reset_config()


def _pdf(tmp_path: Path, name: str = "receipt.pdf", content: bytes = _PDF_BYTES) -> Path:
    path = tmp_path / name
    path.write_bytes(content)
    return path


def _client(detail_payloads: list[Any] | None = None) -> MagicMock:
    mock = MagicMock()
    mock.get_transaction_details = AsyncMock(
        side_effect=list(detail_payloads) if detail_payloads else None,
        return_value=None,
    )
    return mock


def _adapter(
    *,
    params: Any = None,
    media: Any = None,
    registration: Any = None,
    media_error: BaseException | None = None,
    registration_error: BaseException | None = None,
) -> MagicMock:
    adapter = MagicMock()
    adapter.acquire_upload_params = AsyncMock(return_value=params or object())
    if media_error is not None:
        adapter.upload_media = AsyncMock(side_effect=media_error)
    else:
        adapter.upload_media = AsyncMock(return_value=media)
    if registration_error is not None:
        adapter.register_attachment = AsyncMock(side_effect=registration_error)
    else:
        adapter.register_attachment = AsyncMock(return_value=registration)
    return adapter


def _invoke(
    client: MagicMock,
    adapter: MagicMock,
    args: list[str],
):
    with (
        patch.object(module, "get_authenticated_client", return_value=client),
        patch.object(module, "AttachmentUploadAdapter", lambda _client: adapter),
    ):
        return runner.invoke(transactions_app, ["attachments", *args])


def _detail(attachments: list[dict[str, Any]] | None = None, txn_id: str = "txn-1") -> dict:
    return {"getTransaction": {"id": txn_id, "attachments": attachments or []}}


def _outcome(result: Any) -> dict[str, Any]:
    payload = json.loads(result.stdout)
    # Every real mutation outcome emitted by this command must conform to the
    # published schema and its arithmetic invariants. Dry-run previews
    # (status: "dry_run") are deliberately outside the schema family.
    if payload.get("schema_version") == "mutation-outcome.v1":
        errors = sorted(
            _MUTATION_OUTCOME_VALIDATOR.iter_errors(payload),
            key=lambda error: list(error.absolute_path),
        )
        assert not errors, [error.message for error in errors]
        summary = payload["summary"]
        assert summary["total"] == len(payload["items"])
        for status in ("succeeded", "failed", "ambiguous"):
            assert summary[status] == sum(
                1 for item in payload["items"] if item["status"] == status
            )
    return payload


# --- Authorization and invocation shape ------------------------------------


def test_requires_mutation_authorization(tmp_path: Path) -> None:
    set_mutation_authorized(False)
    client = _client()
    adapter = _adapter()
    with patch.object(module, "get_authenticated_client", return_value=client):
        result = runner.invoke(
            transactions_app,
            ["attachments", "add", "--transaction-id", "txn-1", "--file", str(_pdf(tmp_path))],
        )
    assert result.exit_code == 3
    assert "MUTATION_BLOCKED" in (result.stderr or "")
    adapter.upload_media.assert_not_called()
    client.get_transaction_details.assert_not_called()


def test_positional_arguments_are_rejected(tmp_path: Path) -> None:
    result = _invoke(
        _client(),
        _adapter(),
        ["add", "txn-1", "--transaction-id", "txn-1", "--file", str(_pdf(tmp_path))],
    )
    assert result.exit_code == 2
    assert json.loads(result.stderr)["code"] == "INVALID_INPUT"


def test_empty_transaction_id_is_rejected(tmp_path: Path) -> None:
    result = _invoke(
        _client(), _adapter(), ["add", "--transaction-id", "  ", "--file", str(_pdf(tmp_path))]
    )
    assert result.exit_code == 2
    assert json.loads(result.stderr)["details"]["field"] == "transaction_id"


# --- Offline dry-run --------------------------------------------------------


def test_dry_run_is_offline_and_reports_only_local_metadata(tmp_path: Path) -> None:
    client = _client()
    adapter = _adapter()
    path = _pdf(tmp_path)
    with (
        patch.object(
            module,
            "get_authenticated_client",
            side_effect=AssertionError("dry-run must not look up credentials"),
        ),
        patch.object(module, "AttachmentUploadAdapter", lambda _c: adapter),
    ):
        result = runner.invoke(
            transactions_app,
            ["attachments", "add", "--transaction-id", "txn-1", "--file", str(path), "--dry-run"],
        )
    assert result.exit_code == 0
    payload = _outcome(result)
    assert payload["status"] == "dry_run"
    assert payload["operation"] == "transactions.attachments.add"
    assert payload["target"] == {"transaction_id": "txn-1"}
    detail = payload["detail"]
    assert detail["transaction_id"] == "txn-1"
    assert detail["filename"] == "receipt.pdf"
    assert detail["size_bytes"] == len(_PDF_BYTES)
    assert detail["content_type"] == "application/pdf"
    assert str(tmp_path) not in result.stdout
    adapter.upload_media.assert_not_called()
    adapter.acquire_upload_params.assert_not_called()
    client.get_transaction_details.assert_not_called()


def test_dry_run_rejects_unsupported_extension(tmp_path: Path) -> None:
    path = tmp_path / "notes.txt"
    path.write_text("hello")
    result = _invoke(
        _client(),
        _adapter(),
        ["add", "--transaction-id", "txn-1", "--file", str(path), "--dry-run"],
    )
    assert result.exit_code == 2
    assert json.loads(result.stderr)["code"] == "INVALID_INPUT"


def test_dry_run_rejects_missing_and_symlink_and_directory(tmp_path: Path) -> None:
    missing = _invoke(
        _client(),
        _adapter(),
        ["add", "--transaction-id", "txn-1", "--file", str(tmp_path / "nope.pdf"), "--dry-run"],
    )
    assert missing.exit_code == 2

    link = tmp_path / "link.pdf"
    link.symlink_to(_pdf(tmp_path))
    linked = _invoke(
        _client(),
        _adapter(),
        ["add", "--transaction-id", "txn-1", "--file", str(link), "--dry-run"],
    )
    assert linked.exit_code == 2

    directory = _invoke(
        _client(),
        _adapter(),
        ["add", "--transaction-id", "txn-1", "--file", str(tmp_path), "--dry-run"],
    )
    assert directory.exit_code == 2


def test_dry_run_rejects_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "empty.pdf"
    path.write_bytes(b"")
    result = _invoke(
        _client(),
        _adapter(),
        ["add", "--transaction-id", "txn-1", "--file", str(path), "--dry-run"],
    )
    assert result.exit_code == 2
    assert json.loads(result.stderr)["details"]["field"] == "file"


def test_dry_run_rejects_over_limit_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module, "MAX_ATTACHMENT_BYTES", 4)
    result = _invoke(
        _client(),
        _adapter(),
        ["add", "--transaction-id", "txn-1", "--file", str(_pdf(tmp_path)), "--dry-run"],
    )
    assert result.exit_code == 2
    assert json.loads(result.stderr)["details"]["max_bytes"] == 4


# --- Execution-side local validation ---------------------------------------


def test_execution_validates_file_before_authentication(tmp_path: Path) -> None:
    path = tmp_path / "notes.txt"
    path.write_text("hello")
    adapter = _adapter()
    with (
        patch.object(
            module,
            "get_authenticated_client",
            side_effect=AssertionError("invalid file must fail before authentication"),
        ),
        patch.object(module, "AttachmentUploadAdapter", lambda _c: adapter),
    ):
        result = runner.invoke(
            transactions_app,
            ["attachments", "add", "--transaction-id", "txn-1", "--file", str(path)],
        )
    assert result.exit_code == 2
    assert json.loads(result.stderr)["code"] == "INVALID_INPUT"
    adapter.upload_media.assert_not_called()


def test_execution_rejects_content_not_matching_extension(tmp_path: Path) -> None:
    path = tmp_path / "fake.pdf"
    path.write_bytes(b"this is not really a pdf")
    result = _invoke(
        _client(), _adapter(), ["add", "--transaction-id", "txn-1", "--file", str(path)]
    )
    assert result.exit_code == 2
    assert json.loads(result.stderr)["code"] == "INVALID_INPUT"


def test_filename_override_is_validated_by_the_same_policy(tmp_path: Path) -> None:
    path = _pdf(tmp_path)
    bad = _invoke(
        _client(),
        _adapter(),
        ["add", "--transaction-id", "txn-1", "--file", str(path), "--filename", "evil.exe"],
    )
    assert bad.exit_code == 2
    assert json.loads(bad.stderr)["details"]["field"] == "filename"

    traversal = _invoke(
        _client(),
        _adapter(),
        ["add", "--transaction-id", "txn-1", "--file", str(path), "--filename", "../x.pdf"],
    )
    assert traversal.exit_code == 2


def test_no_writes_without_mutation_authorization_after_valid_file(tmp_path: Path) -> None:
    set_mutation_authorized(False)
    adapter = _adapter()
    with patch.object(module, "AttachmentUploadAdapter", lambda _c: adapter):
        result = runner.invoke(
            transactions_app,
            ["attachments", "add", "--transaction-id", "txn-1", "--file", str(_pdf(tmp_path))],
        )
    assert result.exit_code == 3
    adapter.acquire_upload_params.assert_not_called()


# --- Exact target verification ---------------------------------------------


def test_missing_transaction_is_a_structured_not_found(tmp_path: Path) -> None:
    client = _client([{"getTransaction": None}])
    adapter = _adapter()
    result = _invoke(
        client, adapter, ["add", "--transaction-id", "txn-1", "--file", str(_pdf(tmp_path))]
    )
    assert result.exit_code == 1
    assert json.loads(result.stderr)["code"] == "NOT_FOUND"
    adapter.acquire_upload_params.assert_not_called()


def test_target_identity_mismatch_refuses_upload(tmp_path: Path) -> None:
    client = _client([_detail(txn_id="txn-other")])
    adapter = _adapter()
    result = _invoke(
        client, adapter, ["add", "--transaction-id", "txn-1", "--file", str(_pdf(tmp_path))]
    )
    assert result.exit_code == 1
    assert json.loads(result.stderr)["code"] == "API_ERROR"
    adapter.acquire_upload_params.assert_not_called()


# --- Stage outcomes ---------------------------------------------------------


def test_successful_attachment_verifies_and_reports_identity(tmp_path: Path) -> None:
    client = _client([_detail(), _detail([{"id": "att-1", "publicId": "pub-1"}])])
    media = MediaUploadResult(public_id="pub-1", extension="pdf", size_bytes=len(_PDF_BYTES))
    registration = AttachmentRegistration(
        attachment={"id": "att-1", "publicId": "pub-1", "extension": "pdf", "sizeBytes": 99},
        errors=(),
    )
    adapter = _adapter(media=media, registration=registration)
    result = _invoke(
        client, adapter, ["add", "--transaction-id", "txn-1", "--file", str(_pdf(tmp_path))]
    )
    assert result.exit_code == 0
    payload = _outcome(result)
    assert payload["schema_version"] == "mutation-outcome.v1"
    assert payload["operation"] == "transactions.attachments.add"
    assert payload["status"] == "succeeded"
    assert payload["verification"] is None
    assert [item["entity"] for item in payload["items"]] == ["attachment_media", "attachment"]
    attachment = payload["items"][1]
    assert attachment["status"] == "succeeded"
    assert attachment["id"] == "att-1"
    assert attachment["result"] == {
        "transaction_id": "txn-1",
        "attachment_id": "att-1",
        "public_id": "pub-1",
        "filename": "receipt.pdf",
        "extension": "pdf",
        "size_bytes": 99,
    }
    adapter.upload_media.assert_awaited_once()
    adapter.register_attachment.assert_awaited_once()
    assert str(tmp_path) not in result.stdout


def test_media_definitive_failure_is_a_failed_outcome(tmp_path: Path) -> None:
    client = _client([_detail()])
    adapter = _adapter(media_error=MediaUploadError(status_code=413))
    result = _invoke(
        client, adapter, ["add", "--transaction-id", "txn-1", "--file", str(_pdf(tmp_path))]
    )
    assert result.exit_code == 1
    payload = _outcome(result)
    assert payload["status"] == "failed"
    assert payload["items"][0]["entity"] == "attachment_media"
    assert payload["items"][0]["error"]["code"] == "API_ERROR"
    adapter.register_attachment.assert_not_called()


def test_media_ambiguous_is_an_ambiguous_outcome(tmp_path: Path) -> None:
    client = _client([_detail()])
    adapter = _adapter(
        media_error=MutationAmbiguousError(message="timeout", details={"reason": "timeout"})
    )
    result = _invoke(
        client, adapter, ["add", "--transaction-id", "txn-1", "--file", str(_pdf(tmp_path))]
    )
    assert result.exit_code == 4
    payload = _outcome(result)
    assert payload["status"] == "ambiguous"
    assert payload["verification"]["required"] is True
    adapter.register_attachment.assert_not_called()


def test_registration_inner_errors_report_partial(tmp_path: Path) -> None:
    client = _client([_detail()])
    media = MediaUploadResult(public_id="pub-1", extension="pdf", size_bytes=len(_PDF_BYTES))
    registration = AttachmentRegistration(
        attachment=None, errors=({"message": "duplicate attachment"},)
    )
    adapter = _adapter(media=media, registration=registration)
    result = _invoke(
        client, adapter, ["add", "--transaction-id", "txn-1", "--file", str(_pdf(tmp_path))]
    )
    assert result.exit_code == 4
    payload = _outcome(result)
    assert payload["status"] == "partial"
    assert payload["items"][0]["status"] == "succeeded"
    failed = payload["items"][1]
    assert failed["status"] == "failed"
    assert failed["error"]["details"]["payload_errors"][0]["message"] == "duplicate attachment"


def test_registration_ambiguous_reports_partial_with_verification(tmp_path: Path) -> None:
    client = _client([_detail()])
    media = MediaUploadResult(public_id="pub-1", extension="pdf", size_bytes=len(_PDF_BYTES))
    adapter = _adapter(
        media=media,
        registration_error=MutationAmbiguousError(
            message="disconnect", details={"reason": "transport"}
        ),
    )
    result = _invoke(
        client, adapter, ["add", "--transaction-id", "txn-1", "--file", str(_pdf(tmp_path))]
    )
    assert result.exit_code == 4
    payload = _outcome(result)
    assert payload["status"] == "partial"
    assert payload["items"][1]["status"] == "ambiguous"
    assert payload["verification"]["required"] is True


def test_registration_definitive_failure_reports_partial(tmp_path: Path) -> None:
    client = _client([_detail()])
    media = MediaUploadResult(public_id="pub-1", extension="pdf", size_bytes=len(_PDF_BYTES))
    adapter = _adapter(media=media, registration_error=APIError(message="rejected"))
    result = _invoke(
        client, adapter, ["add", "--transaction-id", "txn-1", "--file", str(_pdf(tmp_path))]
    )
    assert result.exit_code == 4
    payload = _outcome(result)
    assert payload["status"] == "partial"
    assert payload["items"][1]["status"] == "failed"


def test_registration_without_identity_is_ambiguous(tmp_path: Path) -> None:
    client = _client([_detail()])
    media = MediaUploadResult(public_id="pub-1", extension="pdf", size_bytes=len(_PDF_BYTES))
    registration = AttachmentRegistration(attachment={}, errors=())
    adapter = _adapter(media=media, registration=registration)
    result = _invoke(
        client, adapter, ["add", "--transaction-id", "txn-1", "--file", str(_pdf(tmp_path))]
    )
    assert result.exit_code == 4
    payload = _outcome(result)
    assert payload["status"] == "partial"
    assert payload["items"][1]["error"]["details"]["reason"] == "missing_identity"


def test_registration_unconfirmed_by_readback_is_ambiguous(tmp_path: Path) -> None:
    # Verify read finds the target, registration returns an identity, and the
    # post-success read does not contain that identity.
    client = _client([_detail(), _detail([{"id": "other-att"}])])
    media = MediaUploadResult(public_id="pub-1", extension="pdf", size_bytes=len(_PDF_BYTES))
    registration = AttachmentRegistration(
        attachment={"id": "att-1", "publicId": "pub-1"}, errors=()
    )
    adapter = _adapter(media=media, registration=registration)
    result = _invoke(
        client, adapter, ["add", "--transaction-id", "txn-1", "--file", str(_pdf(tmp_path))]
    )
    assert result.exit_code == 4
    payload = _outcome(result)
    assert payload["status"] == "partial"
    assert payload["items"][1]["error"]["details"]["reason"] == "verification_mismatch"


def test_repeated_explicit_uploads_upload_each_time(tmp_path: Path) -> None:
    """No filename/size heuristic establishes identity; each request uploads."""
    path = _pdf(tmp_path)
    media = MediaUploadResult(public_id="pub-1", extension="pdf", size_bytes=len(_PDF_BYTES))
    registration = AttachmentRegistration(
        attachment={"id": "att-1", "publicId": "pub-1"}, errors=()
    )
    client = _client(
        [
            _detail(),
            _detail([{"id": "att-1"}]),
            _detail(),
            _detail([{"id": "att-1"}]),
        ]
    )
    adapter = _adapter(media=media, registration=registration)
    for _ in range(2):
        result = _invoke(client, adapter, ["add", "--transaction-id", "txn-1", "--file", str(path)])
        assert result.exit_code == 0
    assert adapter.upload_media.await_count == 2


def test_output_modes_incompatible_with_mutations_are_rejected(tmp_path: Path) -> None:
    from monarch_cli.output import (
        OutputFormat,
        set_default_format,
        set_quiet,
    )

    path = _pdf(tmp_path)
    try:
        set_quiet(True)
        quiet = _invoke(
            _client(), _adapter(), ["add", "--transaction-id", "txn-1", "--file", str(path)]
        )
        assert quiet.exit_code == 2
        assert json.loads(quiet.stderr)["code"] == "INVALID_INPUT"

        set_quiet(False)
        set_default_format(OutputFormat.PLAIN)
        plain = _invoke(
            _client(), _adapter(), ["add", "--transaction-id", "txn-1", "--file", str(path)]
        )
        assert plain.exit_code == 2
        assert json.loads(plain.stderr)["code"] == "INVALID_INPUT"
    finally:
        set_quiet(False)
        set_default_format(None)


def test_media_item_reports_public_upload_identity(tmp_path: Path) -> None:
    client = _client([_detail(), _detail([{"id": "att-1"}])])
    media = MediaUploadResult(public_id="pub-abc", extension="pdf", size_bytes=10)
    registration = AttachmentRegistration(attachment={"id": "att-1"}, errors=())
    adapter = _adapter(media=media, registration=registration)
    result = _invoke(
        client, adapter, ["add", "--transaction-id", "txn-1", "--file", str(_pdf(tmp_path))]
    )
    assert result.exit_code == 0
    payload = _outcome(result)
    assert payload["items"][0]["id"] == "pub-abc"
    # server omitted extension/sizeBytes: fall back to the media result
    attachment = payload["items"][1]["result"]
    assert attachment["extension"] == "pdf"
    assert attachment["size_bytes"] == 10


def test_adapter_boundary_is_the_reviewed_public_class() -> None:
    """The command consumes the reviewed adapter, never the raw client method."""
    source = Path(module.__file__).read_text()
    assert "upload_attachment(" not in source
    assert "AttachmentUploadAdapter" in source
    assert RealAdapter.__name__ == "AttachmentUploadAdapter"
