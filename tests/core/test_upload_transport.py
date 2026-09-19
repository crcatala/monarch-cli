"""Tests for the credential-safe third-party upload transport (mc-sr92).

These tests verify the credential-isolation policy at the transport boundary
by inspecting prepared and captured outbound requests, not by inferring safety
from output redaction. They cover token- and cookie-authenticated client
states, the pinned destination host, redirect refusal, and stage-level outcome
classification.
"""

from __future__ import annotations

import ast
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from unittest import mock

import aiohttp
import pytest
from monarchmoney import MonarchMoney

from monarch_cli.core import upload_transport
from monarch_cli.core.exceptions import APIError, MonarchCLIError, MutationAmbiguousError
from monarch_cli.core.upload_transport import (
    MEDIA_UPLOAD_HOST,
    MEDIA_UPLOAD_URL,
    AttachmentUploadAdapter,
    MediaUploadError,
    MediaUploadResult,
    SignedUploadParams,
    prepare_media_upload,
    upload_media,
)

#: Keys that must never appear on a third-party request.
_CREDENTIAL_HEADER_KEYS = frozenset(
    {
        "authorization",
        "cookie",
        "x-csrftoken",
        "origin",
        "referer",
        "monarch-client",
        "monarch-client-version",
        "proxy-authorization",
    }
)


def _params(
    signature: str = "signed-signature-value",
    api_key: str = "signed-api-key-value",
) -> SignedUploadParams:
    return SignedUploadParams(
        timestamp="1700000000",
        folder="folder-value",
        signature=signature,
        api_key=api_key,
        upload_preset="preset-value",
    )


class _FakeResponse:
    def __init__(
        self,
        status: int,
        payload: Any = None,
        reason: str = "reason",
        json_error: bool = False,
    ) -> None:
        self.status = status
        self.reason = reason
        self._payload = payload
        self._json_error = json_error
        self.json_calls = 0

    async def json(self) -> Any:
        self.json_calls += 1
        if self._json_error:
            raise ValueError("not json")
        return self._payload


class _ResponseContext:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response

    async def __aenter__(self) -> _FakeResponse:
        return self._response

    async def __aexit__(self, *exc: object) -> bool:
        return False


class _FakeSession:
    def __init__(
        self, response: _FakeResponse | None = None, error: Exception | None = None
    ) -> None:
        self._response = response
        self._error = error
        self.calls: list[dict[str, Any]] = []

    def post(self, url: str, **kwargs: Any) -> _ResponseContext:
        self.calls.append({"url": url, **kwargs})
        if self._error is not None:
            raise self._error
        assert self._response is not None
        return _ResponseContext(self._response)


class _FakeSessionFactory:
    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    def __call__(self) -> _FakeSessionFactory:
        return self

    async def __aenter__(self) -> _FakeSession:
        return self._session

    async def __aexit__(self, *exc: object) -> bool:
        return False


def _install_session(monkeypatch: pytest.MonkeyPatch, session: _FakeSession) -> _FakeSession:
    monkeypatch.setattr(upload_transport, "_session_factory", _FakeSessionFactory(session))
    return session


_SUCCESS_PAYLOAD = {
    "public_id": "media/abc123",
    "format": "jpg",
    "bytes": 2048,
    "secure_url": "https://x",
}


class TestPrepareMediaUpload:
    """The prepared request is built only from allowlists."""

    def test_destination_is_pinned_media_endpoint(self) -> None:
        request = prepare_media_upload(_params(), "receipt.jpg")
        assert request.url == MEDIA_UPLOAD_URL
        assert MEDIA_UPLOAD_HOST in request.url
        assert request.url.startswith("https://")

    def test_headers_come_only_from_allowlist(self) -> None:
        request = prepare_media_upload(_params(), "receipt.jpg")
        assert set(request.headers) == {"User-Agent"}
        assert {key.lower() for key in request.headers} & _CREDENTIAL_HEADER_KEYS == set()

    def test_fields_are_allowlisted_signed_fields_only(self) -> None:
        request = prepare_media_upload(_params(), "receipt.jpg")
        assert set(request.fields) == {
            "timestamp",
            "folder",
            "signature",
            "api_key",
            "upload_preset",
        }
        assert request.fields["signature"] == "signed-signature-value"

    def test_repr_redacts_signed_material(self) -> None:
        params = _params()
        request = prepare_media_upload(params, "receipt.jpg")
        assert "signed-signature-value" not in repr(params)
        assert "signed-signature-value" not in repr(request)
        assert "signed-api-key-value" not in repr(request)
        assert "<redacted>" in repr(params)

    def test_content_type_derived_from_filename(self) -> None:
        assert prepare_media_upload(_params(), "receipt.jpg").content_type == "image/jpeg"
        assert (
            prepare_media_upload(_params(), "receipt.unknownext").content_type
            == "application/octet-stream"
        )


class TestCredentialIsolation:
    """Prepared and captured outbound requests carry no Monarch credentials."""

    @pytest.mark.parametrize("auth_mode", ["token", "cookie"])
    async def test_outbound_request_excludes_credentials(
        self, monkeypatch: pytest.MonkeyPatch, auth_mode: str
    ) -> None:
        if auth_mode == "token":
            client = MonarchMoney(token="secret-token-value")
            # The released client carries the token in its own header map.
            assert client._headers["Authorization"] == "Token secret-token-value"
            secret_values = ["secret-token-value"]
        else:
            client = MonarchMoney()
            client.set_cookies({"session_id": "secret-session-value", "csrftoken": "secret-csrf"})
            # Cookie mode removes Authorization but stores cookies/CSRF headers.
            assert "Authorization" not in client._headers
            assert client._cookies is not None
            secret_values = ["secret-session-value", "secret-csrf"]

        adapter = AttachmentUploadAdapter(client)
        session = _install_session(monkeypatch, _FakeSession(_FakeResponse(200, _SUCCESS_PAYLOAD)))

        result = await adapter.upload_media(_params(), b"file-bytes", "receipt.jpg")

        assert result == MediaUploadResult(
            public_id="media/abc123", extension="jpg", size_bytes=2048
        )
        assert len(session.calls) == 1
        headers = session.calls[0]["headers"]
        assert isinstance(headers, Mapping)
        assert {key.lower() for key in headers} & _CREDENTIAL_HEADER_KEYS == set()
        serialized = " ".join(f"{k}: {v}" for k, v in headers.items())
        for secret in secret_values:
            assert secret not in serialized
        # The captured request targets exactly the pinned media endpoint.
        assert session.calls[0]["url"] == MEDIA_UPLOAD_URL

    def test_headers_are_independent_of_client(self) -> None:
        client = MonarchMoney(token="secret-token-value")
        request = prepare_media_upload(_params(), "receipt.jpg")
        assert request.headers == {
            "User-Agent": "monarch-cli (credential-safe attachment transport)"
        }
        assert client._headers["Authorization"].startswith("Token ")


class TestDestinationPolicy:
    """The destination host is pinned and redirects are refused."""

    def test_foreign_host_is_rejected_without_echoing_it(self) -> None:
        with pytest.raises(MonarchCLIError) as exc:
            upload_transport._validated_media_destination("https://evil.example/upload")
        assert "evil.example" not in str(exc.value.message)
        assert "evil.example" not in str(exc.value.details)
        assert exc.value.details["stage"] == "media_upload"

    def test_non_https_destination_is_rejected(self) -> None:
        with pytest.raises(MonarchCLIError):
            upload_transport._validated_media_destination("http://api.cloudinary.com/upload")

    async def test_redirects_are_not_followed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        session = _install_session(
            monkeypatch, _FakeSession(_FakeResponse(302, None, reason="Found"))
        )
        with pytest.raises(MediaUploadError) as exc:
            await upload_media(_params(), b"bytes", "receipt.jpg")
        assert exc.value.details["status_code"] == 302
        assert session.calls[0]["allow_redirects"] is False
        assert len(session.calls) == 1


class TestUploadOutcomeClassification:
    """Stage-level outcomes are distinct and sanitized."""

    async def test_success_returns_media_identity(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _install_session(monkeypatch, _FakeSession(_FakeResponse(200, _SUCCESS_PAYLOAD)))
        result = await upload_media(_params(), b"bytes", "receipt.jpg")
        assert result == MediaUploadResult(
            public_id="media/abc123", extension="jpg", size_bytes=2048
        )
        assert not hasattr(result, "secure_url")

    async def test_client_rejection_is_definitive(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _install_session(monkeypatch, _FakeSession(_FakeResponse(400, {"error": "bad"})))
        with pytest.raises(MediaUploadError) as exc:
            await upload_media(_params(), b"bytes", "receipt.jpg")
        assert exc.value.details["status_code"] == 400
        assert exc.value.details["stage"] == "media_upload"

    async def test_unusable_success_body_is_ambiguous(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _install_session(monkeypatch, _FakeSession(_FakeResponse(200, json_error=True)))
        with pytest.raises(MutationAmbiguousError):
            await upload_media(_params(), b"bytes", "receipt.jpg")

    @pytest.mark.parametrize(
        "payload",
        [
            {"format": "jpg", "bytes": 1},
            {"public_id": "", "format": "jpg", "bytes": 1},
            {"public_id": "x", "bytes": 1},
            {"public_id": "x", "format": "jpg", "bytes": "not-int"},
        ],
    )
    async def test_incomplete_media_identity_is_ambiguous(
        self, monkeypatch: pytest.MonkeyPatch, payload: dict[str, Any]
    ) -> None:
        _install_session(monkeypatch, _FakeSession(_FakeResponse(200, payload)))
        with pytest.raises(MutationAmbiguousError):
            await upload_media(_params(), b"bytes", "receipt.jpg")

    async def test_server_error_is_ambiguous(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _install_session(monkeypatch, _FakeSession(_FakeResponse(503, None)))
        with pytest.raises(MutationAmbiguousError) as exc:
            await upload_media(_params(), b"bytes", "receipt.jpg")
        assert exc.value.details["stage"] == "media_upload"

    async def test_transport_failure_is_ambiguous_and_not_retried(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        session = _install_session(
            monkeypatch, _FakeSession(error=aiohttp.ServerDisconnectedError("dropped"))
        )
        with pytest.raises(MutationAmbiguousError):
            await upload_media(_params(), b"bytes", "receipt.jpg")
        assert len(session.calls) == 1

    async def test_timeout_is_ambiguous(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _install_session(monkeypatch, _FakeSession(error=TimeoutError("timed out")))
        with pytest.raises(MutationAmbiguousError):
            await upload_media(_params(), b"bytes", "receipt.jpg", timeout_seconds=0.01)

    async def test_failures_never_leak_signed_material(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _install_session(monkeypatch, _FakeSession(_FakeResponse(400, {"error": "bad"})))
        with pytest.raises(MediaUploadError) as exc:
            await upload_media(_params(), b"bytes", "receipt.jpg")
        rendered = f"{exc.value.message} {exc.value.details}"
        assert "signed-signature-value" not in rendered
        assert "signed-api-key-value" not in rendered


class TestAdapterStages:
    """The adapter owns the Monarch stages without exposing private methods."""

    @staticmethod
    def _client_with_upload_info(payload: Mapping[str, Any]) -> mock.MagicMock:
        client = mock.MagicMock()
        client._get_transaction_attachment_upload_info = mock.AsyncMock(
            return_value={
                "getTransactionAttachmentUploadInfo": {"info": {"requestParams": payload}}
            }
        )
        return client

    async def test_acquire_upload_params_parses_signed_material(self) -> None:
        client = self._client_with_upload_info(
            {
                "timestamp": 1700000000,
                "folder": "folder-value",
                "signature": "signed-signature-value",
                "api_key": "signed-api-key-value",
                "upload_preset": "preset-value",
            }
        )
        adapter = AttachmentUploadAdapter(client)
        params = await adapter.acquire_upload_params("txn-1")
        assert params == _params()
        client._get_transaction_attachment_upload_info.assert_awaited_once_with(
            transaction_id="txn-1"
        )

    async def test_acquire_upload_params_rejects_missing_fields(self) -> None:
        client = self._client_with_upload_info({"timestamp": 1, "folder": "f"})
        adapter = AttachmentUploadAdapter(client)
        with pytest.raises(APIError) as exc:
            await adapter.acquire_upload_params("txn-1")
        assert exc.value.details["stage"] == "acquire_params"
        assert exc.value.details["missing_fields"]

    async def test_acquire_upload_params_rejects_unexpected_shape(self) -> None:
        client = mock.MagicMock()
        client._get_transaction_attachment_upload_info = mock.AsyncMock(return_value={})
        adapter = AttachmentUploadAdapter(client)
        with pytest.raises(APIError):
            await adapter.acquire_upload_params("txn-1")

    async def test_register_attachment_normalizes_envelope(self) -> None:
        client = mock.MagicMock()
        client._add_transaction_attachment = mock.AsyncMock(
            return_value={
                "addTransactionAttachment": {
                    "attachment": {"id": "att-1", "publicId": "media/abc123"},
                    "errors": [{"message": "nope"}],
                }
            }
        )
        adapter = AttachmentUploadAdapter(client)
        registration = await adapter.register_attachment(
            transaction_id="txn-1",
            filename="receipt.jpg",
            media=MediaUploadResult(public_id="media/abc123", extension="jpg", size_bytes=2048),
        )
        assert registration.attachment == {"id": "att-1", "publicId": "media/abc123"}
        assert registration.errors == ({"message": "nope"},)
        client._add_transaction_attachment.assert_awaited_once_with(
            transaction_id="txn-1",
            filename="receipt.jpg",
            public_id="media/abc123",
            extension="jpg",
            size_bytes=2048,
        )

    async def test_register_attachment_rejects_unexpected_shape(self) -> None:
        client = mock.MagicMock()
        client._add_transaction_attachment = mock.AsyncMock(return_value={"unexpected": True})
        adapter = AttachmentUploadAdapter(client)
        with pytest.raises(APIError) as exc:
            await adapter.register_attachment(
                transaction_id="txn-1",
                filename="receipt.jpg",
                media=MediaUploadResult(public_id="p", extension="jpg", size_bytes=1),
            )
        assert exc.value.details["stage"] == "register_attachment"

    async def test_adapter_upload_media_delegates_to_transport(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = MonarchMoney(token="secret-token-value")
        adapter = AttachmentUploadAdapter(client)
        _install_session(monkeypatch, _FakeSession(_FakeResponse(200, _SUCCESS_PAYLOAD)))
        result = await adapter.upload_media(_params(), b"bytes", "receipt.jpg")
        assert result.public_id == "media/abc123"


class TestNoUnsafeUpstreamUsage:
    """Regression guards for the credential-isolation boundary."""

    _PRIVATE_STAGE_METHODS = frozenset(
        {"_get_transaction_attachment_upload_info", "_add_transaction_attachment"}
    )

    @staticmethod
    def _source_files() -> list[Path]:
        src = Path(upload_transport.__file__).resolve().parents[1]
        return sorted(src.rglob("*.py"))

    @staticmethod
    def _attribute_calls(path: Path) -> set[str]:
        """Return names of attribute-call expressions in a source file.

        Uses the AST so documentation mentions do not count as calls.
        """
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                names.add(node.func.attr)
        return names

    def test_no_code_calls_upstream_upload_attachment(self) -> None:
        offenders = [
            path.name
            for path in self._source_files()
            if "upload_attachment" in self._attribute_calls(path)
        ]
        assert offenders == [], f"unsafe upload_attachment() call in {offenders}"

    def test_private_stage_methods_are_only_referenced_by_the_adapter(self) -> None:
        references: list[str] = []
        for path in self._source_files():
            if self._attribute_calls(path) & self._PRIVATE_STAGE_METHODS:
                references.append(path.name)
        assert references == ["upload_transport.py"], (
            "upstream private upload methods must be called only by the "
            f"upload-transport adapter; found {references}"
        )
