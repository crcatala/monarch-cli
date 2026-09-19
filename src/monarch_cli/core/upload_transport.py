"""Credential-safe third-party upload transport for transaction attachments.

Why this module exists
======================

The released ``monarchmoneycommunity`` client (1.5.2, the newest release at the
time of writing) has no public, credential-isolated transaction-attachment
upload. ``MonarchMoney.upload_attachment()`` performs the third-party media
upload through ``MonarchMoney._upload_form_data()``, which copies the
authenticated client's outbound headers and only removes ``Accept`` /
``Content-Type`` (and, for non-Monarch hosts, the cookie/CSRF headers). In
token-authentication mode that leaves the Monarch ``Authorization: Token ...``
header attached to the request sent to the third-party media host, leaking
Monarch credentials off-origin. Because this CLI authenticates with a token,
that path must not be used.

There is no released upstream fix to depend on, so this module owns a local,
narrow adapter boundary instead. It is deliberately not a general HTTP client:

* third-party request headers and signed form fields are built from explicit
  destination-specific allowlists, never by copying and pruning the Monarch
  client's headers;
* the destination is pinned to the verified media upload endpoint and
  redirects are never followed, so credential material can never be forwarded
  across origins;
* each stage of the upload path is exposed separately -- Monarch signed
  parameter acquisition, the third-party media upload, and Monarch attachment
  registration -- so callers keep stage-level identity for the
  ``mutation-outcome.v1`` contract;
* signed parameters, destination details, and media-host responses are treated
  as sensitive and never appear in logs, structured errors, or diagnostics.

Compatibility boundary and maintenance assumptions
==================================================

This ticket owns only the credential-safe media transport and the compatibility
decomposition that keeps upstream private methods out of commands and services.
The authenticated Monarch stages (signed parameters and attachment
registration) call the released client's private
``_get_transaction_attachment_upload_info`` / ``_add_transaction_attachment``
methods because the released client exposes no public per-stage interface.
Commands and services never call those methods directly; this module is the
single owner. The expected upstream shapes are asserted by the compatibility
tests in ``tests/core/test_client_interface.py``.

If a future ``monarchmoneycommunity`` release exposes a public, credential-safe,
stage-aware upload interface, replace this adapter with a thin delegation and
delete the private-method bridge here. The credential-isolation tests
(``tests/core/test_upload_transport.py``) must keep passing across that change.
"""

from __future__ import annotations

import asyncio
import mimetypes
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import aiohttp
from monarchmoney import MonarchMoney  # type: ignore[import-untyped]

from .async_utils import AMBIGUOUS_TRANSPORT_EXCEPTIONS
from .exceptions import APIError, ErrorCode, MonarchCLIError, MutationAmbiguousError

#: The verified third-party media upload destination. The signed-parameter
#: response also returns a server-supplied ``path``; that value is never used,
#: so the destination cannot be steered by remote data.
MEDIA_UPLOAD_HOST = "api.cloudinary.com"
MEDIA_UPLOAD_URL = "https://api.cloudinary.com/v1_1/monarch-money/image/upload/"

#: Destination-specific header allowlist for the media host. The media endpoint
#: rejects caller-supplied ``Accept`` / ``Content-Type`` (aiohttp sets the
#: multipart one) and never needs Monarch credentials, cookies, CSRF, or
#: session headers. Nothing here is copied from the authenticated client.
_MEDIA_HEADER_ALLOWLIST: Mapping[str, str] = {
    "User-Agent": "monarch-cli (credential-safe attachment transport)",
}

#: Destination-specific signed form-field allowlist. Only these keys are sent,
#: read from the acquired signed parameters.
_SIGNED_FORM_FIELDS: tuple[str, ...] = (
    "timestamp",
    "folder",
    "signature",
    "api_key",
    "upload_preset",
)

#: Transport seam for tests. Production uses a fresh ``aiohttp.ClientSession``.
_session_factory: Callable[[], Any] = aiohttp.ClientSession


class MediaUploadError(MonarchCLIError):
    """Definitive third-party media-upload rejection.

    Raised when the media host gave a definitive negative answer (a rejected
    request or a refused redirect) that did not create an asset. Messages and
    details never contain signed parameters, destination details, or the raw
    response body.
    """

    def __init__(
        self,
        message: str = "The media host rejected the attachment upload.",
        *,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        full_details = dict(details or {})
        full_details["stage"] = "media_upload"
        if status_code is not None:
            full_details["status_code"] = status_code
        super().__init__(
            message=message,
            code=ErrorCode.API_ERROR,
            details=full_details,
            exit_code=1,
        )


@dataclass(frozen=True)
class SignedUploadParams:
    """Signed parameters for one third-party media upload (sensitive).

    These values authorize a single upload to the media host. They are never
    logged, emitted in structured output, or copied into diagnostics, and the
    repr is intentionally redacted.
    """

    timestamp: str
    folder: str
    signature: str
    api_key: str
    upload_preset: str

    def form_fields(self) -> dict[str, str]:
        """Return the allowlisted signed form fields to send."""
        return {
            "timestamp": self.timestamp,
            "folder": self.folder,
            "signature": self.signature,
            "api_key": self.api_key,
            "upload_preset": self.upload_preset,
        }

    def __repr__(self) -> str:
        return "SignedUploadParams(<redacted>)"


@dataclass(frozen=True)
class MediaUploadResult:
    """Media-host identity/metadata needed to register an attachment.

    Contains only what the registration stage requires; the media host's
    response body, URLs, and signed parameters are never carried forward.
    """

    public_id: str
    extension: str
    size_bytes: int


@dataclass(frozen=True)
class AttachmentRegistration:
    """Normalized outcome of the Monarch attachment-registration stage.

    ``attachment`` is the returned attachment object when present;
    ``errors`` are the sanitized inner payload errors. Interpreting these
    into a mutation-outcome classification belongs to the consuming workflow,
    not to this transport boundary.
    """

    attachment: Mapping[str, Any] | None
    errors: tuple[Mapping[str, Any], ...]


@dataclass(frozen=True)
class MediaUploadRequest:
    """A prepared, credential-free outbound media-upload request.

    Exposed so tests can inspect exactly what would be sent to the media host.
    The repr is redacted because ``fields`` carry signed material.
    """

    url: str
    headers: Mapping[str, str]
    fields: Mapping[str, str]
    filename: str
    content_type: str

    def __repr__(self) -> str:
        return (
            f"MediaUploadRequest(url={self.url!r}, headers={dict(self.headers)!r}, "
            f"filename={self.filename!r}, fields=<redacted>)"
        )


@dataclass(frozen=True)
class _RawResponse:
    """Internal record of a media-host response (never exposed to callers)."""

    status: int
    reason: str
    payload: Any
    parse_error: bool


def _validated_media_destination(url: str) -> str:
    """Return ``url`` only if it is the pinned HTTPS media destination.

    The destination is a module constant rather than caller- or server-supplied
    input, so this is a defensive invariant: it guarantees that the only host
    ever contacted is the verified media endpoint, over HTTPS.

    Raises:
        MonarchCLIError: If the URL is not the pinned media destination. The
            rejected URL is never echoed, so remote data cannot smuggle a
            value into diagnostics.
    """
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != MEDIA_UPLOAD_HOST:
        raise MonarchCLIError(
            message=("Refusing to send a media upload outside the pinned media destination host."),
            code=ErrorCode.POLICY_VIOLATION,
            details={"stage": "media_upload"},
            exit_code=1,
        )
    return url


def prepare_media_upload(params: SignedUploadParams, filename: str) -> MediaUploadRequest:
    """Build the credential-free outbound media-upload request.

    Headers come from an explicit destination allowlist and form fields from
    the signed-field allowlist. Nothing is copied from the authenticated
    Monarch client, so no authorization, cookie, CSRF, or session header can
    reach the third-party host regardless of the client's authentication mode.

    Args:
        params: Signed parameters acquired for this upload.
        filename: The already-validated destination filename (policy is owned
            by the calling workflow).

    Returns:
        The prepared request.
    """
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return MediaUploadRequest(
        url=_validated_media_destination(MEDIA_UPLOAD_URL),
        headers=dict(_MEDIA_HEADER_ALLOWLIST),
        fields=params.form_fields(),
        filename=filename,
        content_type=content_type,
    )


async def _post_media_request(request: MediaUploadRequest, file_content: bytes) -> _RawResponse:
    """Send one media upload with redirects disabled; return the raw response.

    Redirects are never followed (``allow_redirects=False``), so a 3xx cannot
    forward request headers to another origin. The response body is parsed
    only to extract the media identity fields.
    """
    form = aiohttp.FormData()
    form.add_field(
        "file",
        file_content,
        filename=request.filename,
        content_type=request.content_type,
    )
    for name, value in request.fields.items():
        form.add_field(name, value)

    async with (
        _session_factory() as session,
        session.post(
            request.url,
            data=form,
            headers=dict(request.headers),
            allow_redirects=False,
        ) as response,
    ):
        status = int(response.status)
        reason = str(response.reason or "")
        payload: Any = None
        parse_error = False
        try:
            payload = await response.json()
        except Exception:
            parse_error = True
        return _RawResponse(
            status=status,
            reason=reason,
            payload=payload,
            parse_error=parse_error,
        )


def _parse_media_result(response: _RawResponse) -> MediaUploadResult | None:
    """Extract the media identity from a successful response; None if unusable.

    The raw payload is dropped immediately: only the identity fields needed by
    the registration stage are retained.
    """
    if response.parse_error or not isinstance(response.payload, Mapping):
        return None
    payload = response.payload
    public_id = payload.get("public_id")
    extension = payload.get("format")
    size_bytes = payload.get("bytes")
    if not isinstance(public_id, str) or not public_id:
        return None
    if not isinstance(extension, str) or not extension:
        return None
    if not isinstance(size_bytes, int) or isinstance(size_bytes, bool) or size_bytes < 0:
        return None
    return MediaUploadResult(
        public_id=public_id,
        extension=extension,
        size_bytes=size_bytes,
    )


async def upload_media(
    params: SignedUploadParams,
    file_content: bytes,
    filename: str,
    *,
    timeout_seconds: float | None = None,
) -> MediaUploadResult:
    """Upload file bytes to the media host and return the media identity.

    This function performs exactly one attempt and never retries: a retry after
    the request may have been dispatched could create a second orphaned asset.
    Outcomes are classified honestly:

    - success (2xx with usable media identity) returns :class:`MediaUploadResult`;
    - a refused redirect or a client rejection (3xx/4xx) raises
      :class:`MediaUploadError` (definitive failure, no asset created);
    - a server error, an unusable success body, a timeout, or a transport
      failure raises :class:`MutationAmbiguousError`, because the media host
      may have created an asset the caller must reconcile.

    The signed parameters and raw response are never included in errors.
    """
    request = prepare_media_upload(params, filename)

    try:
        if timeout_seconds is None:
            response = await _post_media_request(request, file_content)
        else:
            async with asyncio.timeout(timeout_seconds):
                response = await _post_media_request(request, file_content)
    except AMBIGUOUS_TRANSPORT_EXCEPTIONS as e:
        raise MutationAmbiguousError(
            message=(
                "The attachment media upload could not be confirmed (transport "
                "failure after the request may have been dispatched). The media "
                "host may have created an asset; do not retry blindly."
            ),
            details={"stage": "media_upload", "remote_state": "unknown"},
        ) from e

    status = response.status
    if 200 <= status < 300:
        result = _parse_media_result(response)
        if result is None:
            raise MutationAmbiguousError(
                message=(
                    "The media host accepted the attachment upload but returned "
                    "no usable media identity. An asset may exist; do not retry "
                    "blindly."
                ),
                details={"stage": "media_upload", "remote_state": "unknown"},
            )
        return result
    if 300 <= status < 400:
        raise MediaUploadError(
            message=(
                "The media host returned a redirect, which is refused so "
                "request headers are never forwarded to another origin. No "
                "asset was created."
            ),
            status_code=status,
        )
    if 400 <= status < 500:
        raise MediaUploadError(
            message="The media host rejected the attachment upload. No asset was created.",
            status_code=status,
        )
    raise MutationAmbiguousError(
        message=(
            "The media host returned an error after the attachment upload was "
            "dispatched. An asset may have been created; do not retry blindly."
        ),
        details={"stage": "media_upload", "remote_state": "unknown"},
    )


def _parse_signed_params(raw: Any) -> SignedUploadParams:
    """Parse a signed-parameter payload, rejecting unexpected shapes.

    Only field *names* are reported when material is missing; signed values are
    never echoed.
    """
    if not isinstance(raw, Mapping):
        raise APIError(
            message="The attachment upload parameters were not in the expected shape.",
            details={"stage": "acquire_params"},
        )
    missing = [name for name in _SIGNED_FORM_FIELDS if raw.get(name) in (None, "")]
    if missing:
        raise APIError(
            message="The attachment upload parameters were incomplete.",
            details={"stage": "acquire_params", "missing_fields": missing},
        )
    return SignedUploadParams(
        timestamp=str(raw["timestamp"]),
        folder=str(raw["folder"]),
        signature=str(raw["signature"]),
        api_key=str(raw["api_key"]),
        upload_preset=str(raw["upload_preset"]),
    )


class AttachmentUploadAdapter:
    """Public adapter boundary for the transaction-attachment upload path.

    Commands and services consume only this class for attachment uploads. It
    keeps the authenticated Monarch stages (signed parameter acquisition and
    attachment registration) separate from the credential-safe third-party
    media transport, and never exposes the upstream client's private methods
    or ``MonarchMoney.upload_attachment()``.
    """

    def __init__(self, client: MonarchMoney) -> None:
        self._client = client

    async def acquire_upload_params(self, transaction_id: str) -> SignedUploadParams:
        """Acquire signed parameters for one transaction attachment upload.

        This is the authenticated Monarch stage. It calls the released client's
        compatibility method, parses the response, and returns the signed
        material needed by :func:`upload_media`; no third-party request is made.
        """
        response = await self._client._get_transaction_attachment_upload_info(
            transaction_id=transaction_id
        )
        try:
            params = response["getTransactionAttachmentUploadInfo"]["info"]["requestParams"]
        except (KeyError, TypeError) as e:
            raise APIError(
                message="The attachment upload parameters response was not in the expected shape.",
                details={"stage": "acquire_params"},
            ) from e
        return _parse_signed_params(params)

    async def upload_media(
        self,
        params: SignedUploadParams,
        file_content: bytes,
        filename: str,
        *,
        timeout_seconds: float | None = None,
    ) -> MediaUploadResult:
        """Upload file bytes to the credential-safe media transport."""
        return await upload_media(
            params,
            file_content,
            filename,
            timeout_seconds=timeout_seconds,
        )

    async def register_attachment(
        self,
        *,
        transaction_id: str,
        filename: str,
        media: MediaUploadResult,
    ) -> AttachmentRegistration:
        """Register an uploaded media asset on a transaction.

        This is the authenticated Monarch stage. It calls the released client's
        compatibility method and normalizes the envelope; interpreting the
        result into a mutation-outcome classification belongs to the consuming
        workflow.
        """
        response = await self._client._add_transaction_attachment(
            transaction_id=transaction_id,
            filename=filename,
            public_id=media.public_id,
            extension=media.extension,
            size_bytes=media.size_bytes,
        )
        data = response.get("addTransactionAttachment") if isinstance(response, Mapping) else None
        if not isinstance(data, Mapping):
            raise APIError(
                message="The attachment registration response was not in the expected shape.",
                details={"stage": "register_attachment"},
            )
        attachment = data.get("attachment")
        raw_errors = data.get("errors")
        errors: tuple[Mapping[str, Any], ...] = ()
        if isinstance(raw_errors, list):
            errors = tuple(item for item in raw_errors if isinstance(item, Mapping))
        return AttachmentRegistration(
            attachment=attachment if isinstance(attachment, Mapping) else None,
            errors=errors,
        )


__all__ = [
    "MEDIA_UPLOAD_HOST",
    "MEDIA_UPLOAD_URL",
    "AttachmentRegistration",
    "AttachmentUploadAdapter",
    "MediaUploadError",
    "MediaUploadRequest",
    "MediaUploadResult",
    "SignedUploadParams",
    "prepare_media_upload",
    "upload_media",
]
