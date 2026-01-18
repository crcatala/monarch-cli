"""Tests for monarch_cli.core.adapter module."""

from __future__ import annotations

from unittest import mock

import pytest

from monarch_cli.core.adapter import (
    extract_token_from_client,
    get_authenticated_client,
    reset_client,
)
from monarch_cli.core.exceptions import AuthenticationError


class TestGetAuthenticatedClient:
    """Tests for get_authenticated_client function."""

    def setup_method(self) -> None:
        """Reset client before each test."""
        reset_client()

    def teardown_method(self) -> None:
        """Reset client after each test."""
        reset_client()

    @mock.patch("monarch_cli.core.adapter.get_session_token")
    @mock.patch("monarch_cli.core.adapter.MonarchMoney")
    def test_creates_client_with_token(
        self,
        mock_monarch: mock.MagicMock,
        mock_get_token: mock.MagicMock,
    ) -> None:
        """Should create MonarchMoney client with stored token."""
        mock_get_token.return_value = "test-token"
        mock_client = mock.MagicMock()
        mock_monarch.return_value = mock_client

        result = get_authenticated_client()

        mock_monarch.assert_called_once_with(token="test-token")
        assert result is mock_client

    @mock.patch("monarch_cli.core.adapter.get_session_token")
    def test_raises_auth_error_when_no_token(self, mock_get_token: mock.MagicMock) -> None:
        """Should raise AuthenticationError when no token available."""
        mock_get_token.return_value = None

        with pytest.raises(AuthenticationError):
            get_authenticated_client()

    @mock.patch("monarch_cli.core.adapter.get_session_token")
    @mock.patch("monarch_cli.core.adapter.MonarchMoney")
    def test_caches_client(
        self,
        mock_monarch: mock.MagicMock,
        mock_get_token: mock.MagicMock,
    ) -> None:
        """Should cache and return same client instance."""
        mock_get_token.return_value = "test-token"
        mock_client = mock.MagicMock()
        mock_monarch.return_value = mock_client

        client1 = get_authenticated_client()
        client2 = get_authenticated_client()

        # MonarchMoney should only be instantiated once
        mock_monarch.assert_called_once()
        assert client1 is client2

    @mock.patch("monarch_cli.core.adapter.get_session_token")
    @mock.patch("monarch_cli.core.adapter.MonarchMoney")
    def test_reset_clears_cache(
        self,
        mock_monarch: mock.MagicMock,
        mock_get_token: mock.MagicMock,
    ) -> None:
        """reset_client should clear cached client."""
        mock_get_token.return_value = "test-token"
        mock_client1 = mock.MagicMock()
        mock_client2 = mock.MagicMock()
        mock_monarch.side_effect = [mock_client1, mock_client2]

        client1 = get_authenticated_client()
        reset_client()
        client2 = get_authenticated_client()

        # Should have created two different clients
        assert mock_monarch.call_count == 2
        assert client1 is not client2


class TestExtractTokenFromClient:
    """Tests for extract_token_from_client function."""

    def test_extracts_token(self) -> None:
        """Should extract token from client."""
        mock_client = mock.MagicMock()
        mock_client.token = "extracted-token"

        result = extract_token_from_client(mock_client)

        assert result == "extracted-token"

    def test_returns_none_when_no_token(self) -> None:
        """Should return None when client has no token."""
        mock_client = mock.MagicMock()
        mock_client.token = None

        result = extract_token_from_client(mock_client)

        assert result is None


class TestResetClient:
    """Tests for reset_client function."""

    @mock.patch("monarch_cli.core.adapter.get_session_token")
    @mock.patch("monarch_cli.core.adapter.MonarchMoney")
    def test_allows_new_client_creation(
        self,
        mock_monarch: mock.MagicMock,
        mock_get_token: mock.MagicMock,
    ) -> None:
        """After reset, new client should be created."""
        mock_get_token.return_value = "token"

        # First client
        get_authenticated_client()
        assert mock_monarch.call_count == 1

        # Reset
        reset_client()

        # Second client
        get_authenticated_client()
        assert mock_monarch.call_count == 2

    def test_reset_when_no_client(self) -> None:
        """reset_client should not raise when no client exists."""
        reset_client()  # Should not raise
        reset_client()  # Multiple resets should be fine
