"""
Exception hierarchy for Monarch CLI.

All custom exceptions inherit from MonarchCLIError and provide structured output
for AI agent consumption via to_dict() method.
"""

from enum import Enum
from typing import Any


class ErrorCode(Enum):
    """Error codes for structured error handling.

    These codes are designed for AI agent consumption, providing machine-readable
    error classification.
    """

    AUTH_REQUIRED = "AUTH_REQUIRED"
    AUTH_EXPIRED = "AUTH_EXPIRED"
    AUTH_FAILED = "AUTH_FAILED"
    NOT_FOUND = "NOT_FOUND"
    INVALID_INPUT = "INVALID_INPUT"
    API_ERROR = "API_ERROR"
    RATE_LIMITED = "RATE_LIMITED"
    NETWORK_ERROR = "NETWORK_ERROR"
    TIMEOUT = "TIMEOUT"
    UPSTREAM_UNAVAILABLE = "UPSTREAM_UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


class MonarchCLIError(Exception):
    """Base exception for all Monarch CLI errors.

    Provides structured error output for AI agent consumption.

    Attributes:
        message: Human-readable error message.
        code: ErrorCode enum value for machine-readable classification.
        details: Optional dict with additional context.
        exit_code: Process exit code (1 for most errors, 2 for usage errors).
    """

    def __init__(
        self,
        message: str = "An error occurred",
        code: ErrorCode = ErrorCode.UNKNOWN,
        details: dict[str, Any] | None = None,
        exit_code: int = 1,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}
        self.exit_code = exit_code

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-serializable dict for structured output.

        Returns:
            Dict with error=True, code, message, and details fields.
        """
        return {
            "error": True,
            "code": self.code.value,
            "message": self.message,
            "details": self.details,
        }


class AuthenticationError(MonarchCLIError):
    """Not authenticated. Run 'monarch auth login' first."""

    def __init__(
        self,
        message: str = "Not authenticated. Run 'monarch auth login' first.",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code=ErrorCode.AUTH_REQUIRED,
            details=details,
            exit_code=1,
        )


class AuthExpiredError(MonarchCLIError):
    """Session expired. Re-authenticate."""

    def __init__(
        self,
        message: str = "Session expired. Please re-authenticate with 'monarch auth login'.",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code=ErrorCode.AUTH_EXPIRED,
            details=details,
            exit_code=1,
        )


class NotFoundError(MonarchCLIError):
    """Resource not found."""

    def __init__(
        self,
        message: str = "Resource not found",
        resource_type: str | None = None,
        resource_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        full_details = details or {}
        if resource_type:
            full_details["resource_type"] = resource_type
        if resource_id:
            full_details["resource_id"] = resource_id
        super().__init__(
            message=message,
            code=ErrorCode.NOT_FOUND,
            details=full_details,
            exit_code=1,
        )


class ValidationError(MonarchCLIError):
    """Input validation error."""

    def __init__(
        self,
        message: str = "Invalid input",
        field: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        full_details = details or {}
        if field:
            full_details["field"] = field
        super().__init__(
            message=message,
            code=ErrorCode.INVALID_INPUT,
            details=full_details,
            exit_code=2,  # Usage error
        )


class APIError(MonarchCLIError):
    """Monarch Money API error."""

    def __init__(
        self,
        message: str = "Monarch Money API error",
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        full_details = details or {}
        if status_code is not None:
            full_details["status_code"] = status_code
        super().__init__(
            message=message,
            code=ErrorCode.API_ERROR,
            details=full_details,
            exit_code=1,
        )


class RateLimitError(MonarchCLIError):
    """Rate limit exceeded."""

    def __init__(
        self,
        message: str = "Rate limit exceeded. Please try again later.",
        retry_after_seconds: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        full_details = details or {}
        if retry_after_seconds is not None:
            full_details["retry_after_seconds"] = retry_after_seconds
        super().__init__(
            message=message,
            code=ErrorCode.RATE_LIMITED,
            details=full_details,
            exit_code=1,
        )


class NetworkError(MonarchCLIError):
    """Network connectivity error."""

    def __init__(
        self,
        message: str = "Network error. Please check your connection and try again.",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code=ErrorCode.NETWORK_ERROR,
            details=details,
            exit_code=1,
        )
