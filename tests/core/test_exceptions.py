"""Tests for monarch_cli.core.exceptions module."""

from monarch_cli.core.exceptions import (
    APIError,
    AuthenticationError,
    AuthExpiredError,
    ErrorCode,
    MonarchCLIError,
    NetworkError,
    NotFoundError,
    RateLimitError,
    ValidationError,
)


class TestErrorCode:
    """Tests for ErrorCode enum."""

    def test_all_codes_have_string_values(self) -> None:
        """All error codes should have string values matching their names."""
        for code in ErrorCode:
            assert code.value == code.name

    def test_expected_codes_exist(self) -> None:
        """Expected error codes should exist."""
        expected = [
            "AUTH_REQUIRED",
            "AUTH_EXPIRED",
            "AUTH_FAILED",
            "NOT_FOUND",
            "INVALID_INPUT",
            "API_ERROR",
            "RATE_LIMITED",
            "NETWORK_ERROR",
            "TIMEOUT",
            "UPSTREAM_UNAVAILABLE",
            "UNKNOWN",
        ]
        actual = [code.name for code in ErrorCode]
        for code in expected:
            assert code in actual


class TestMonarchCLIError:
    """Tests for base MonarchCLIError class."""

    def test_default_values(self) -> None:
        """Default error should have sensible defaults."""
        error = MonarchCLIError()
        assert error.message == "An error occurred"
        assert error.code == ErrorCode.UNKNOWN
        assert error.details == {}
        assert error.exit_code == 1

    def test_custom_values(self) -> None:
        """Custom values should be preserved."""
        error = MonarchCLIError(
            message="Custom message",
            code=ErrorCode.API_ERROR,
            details={"key": "value"},
            exit_code=42,
        )
        assert error.message == "Custom message"
        assert error.code == ErrorCode.API_ERROR
        assert error.details == {"key": "value"}
        assert error.exit_code == 42

    def test_to_dict(self) -> None:
        """to_dict should return JSON-serializable dict."""
        error = MonarchCLIError(
            message="Test error",
            code=ErrorCode.NETWORK_ERROR,
            details={"retry": True},
        )
        result = error.to_dict()
        assert result == {
            "error": True,
            "code": "NETWORK_ERROR",
            "message": "Test error",
            "details": {"retry": True},
        }

    def test_str_representation(self) -> None:
        """str() should return the message."""
        error = MonarchCLIError(message="Test message")
        assert str(error) == "Test message"


class TestAuthenticationError:
    """Tests for AuthenticationError."""

    def test_default_message(self) -> None:
        """Default message should guide user to login."""
        error = AuthenticationError()
        assert "monarch auth login" in error.message
        assert error.code == ErrorCode.AUTH_REQUIRED
        assert error.exit_code == 1

    def test_custom_message(self) -> None:
        """Custom message should be preserved."""
        error = AuthenticationError(message="Custom auth error")
        assert error.message == "Custom auth error"


class TestAuthExpiredError:
    """Tests for AuthExpiredError."""

    def test_default_message(self) -> None:
        """Default message should mention re-authentication."""
        error = AuthExpiredError()
        assert "expired" in error.message.lower()
        assert error.code == ErrorCode.AUTH_EXPIRED


class TestNotFoundError:
    """Tests for NotFoundError."""

    def test_default_message(self) -> None:
        """Default message should mention resource not found."""
        error = NotFoundError()
        assert error.message == "Resource not found"
        assert error.code == ErrorCode.NOT_FOUND

    def test_resource_details(self) -> None:
        """Resource type and ID should be included in details."""
        error = NotFoundError(
            message="Account not found",
            resource_type="account",
            resource_id="abc123",
        )
        assert error.details["resource_type"] == "account"
        assert error.details["resource_id"] == "abc123"

    def test_details_merged(self) -> None:
        """Additional details should be merged with resource info."""
        error = NotFoundError(
            resource_type="account",
            details={"extra": "info"},
        )
        assert error.details["resource_type"] == "account"
        assert error.details["extra"] == "info"


class TestValidationError:
    """Tests for ValidationError."""

    def test_exit_code_is_2(self) -> None:
        """Validation errors should use exit code 2 (usage error)."""
        error = ValidationError()
        assert error.exit_code == 2
        assert error.code == ErrorCode.INVALID_INPUT

    def test_field_in_details(self) -> None:
        """Field name should be included in details."""
        error = ValidationError(field="email")
        assert error.details["field"] == "email"


class TestAPIError:
    """Tests for APIError."""

    def test_status_code_in_details(self) -> None:
        """HTTP status code should be included in details."""
        error = APIError(status_code=404)
        assert error.details["status_code"] == 404
        assert error.code == ErrorCode.API_ERROR


class TestRateLimitError:
    """Tests for RateLimitError."""

    def test_retry_after_in_details(self) -> None:
        """Retry-after should be included in details."""
        error = RateLimitError(retry_after_seconds=60)
        assert error.details["retry_after_seconds"] == 60
        assert error.code == ErrorCode.RATE_LIMITED


class TestNetworkError:
    """Tests for NetworkError."""

    def test_default_message(self) -> None:
        """Default message should mention network error."""
        error = NetworkError()
        assert "network" in error.message.lower()
        assert error.code == ErrorCode.NETWORK_ERROR
