"""Tests for error handler decorator."""

from __future__ import annotations

from unittest import mock

import typer
from typer.testing import CliRunner

from monarch_cli.core.error_handler import handle_errors
from monarch_cli.core.exceptions import (
    APIError,
    AuthenticationError,
    MonarchCLIError,
    ValidationError,
)

# Create a Typer app for testing the decorator
# Named with underscore prefix to avoid pytest collection warning
_app = typer.Typer()
runner = CliRunner()


@_app.command()
@handle_errors
def success_cmd() -> None:
    """Command that succeeds."""
    print("success")


@_app.command()
@handle_errors
def raises_auth_error() -> None:
    """Command that raises AuthenticationError."""
    raise AuthenticationError()


@_app.command()
@handle_errors
def raises_api_error() -> None:
    """Command that raises APIError."""
    raise APIError("API request failed", status_code=500)


@_app.command()
@handle_errors
def raises_validation_error() -> None:
    """Command that raises ValidationError."""
    raise ValidationError("Invalid input", field="email")


@_app.command()
@handle_errors
def raises_unexpected() -> None:
    """Command that raises unexpected error."""
    raise ValueError("something went wrong")


@_app.command()
@handle_errors
def raises_keyboard_interrupt() -> None:
    """Command that raises KeyboardInterrupt."""
    raise KeyboardInterrupt()


@_app.command()
@handle_errors
def raises_custom_exit_code() -> None:
    """Command that raises error with custom exit code."""
    raise MonarchCLIError("Custom error", exit_code=42)


class TestHandleErrorsSuccess:
    """Tests for successful command execution."""

    def test_success_passes_through(self) -> None:
        """Successful commands should work normally."""
        result = runner.invoke(_app, ["success-cmd"])
        assert result.exit_code == 0
        assert "success" in result.stdout

    def test_success_no_stderr_errors(self) -> None:
        """Successful commands should not output errors to stderr."""
        result = runner.invoke(_app, ["success-cmd"])
        assert result.exit_code == 0
        assert result.stderr == ""


class TestHandleErrorsMonarchCLIError:
    """Tests for MonarchCLIError handling."""

    def test_catches_authentication_error(self) -> None:
        """Should catch AuthenticationError and output structured error."""
        result = runner.invoke(_app, ["raises-auth-error"])
        assert result.exit_code == 1
        assert "AUTH_REQUIRED" in result.stderr
        assert '"error": true' in result.stderr

    def test_catches_api_error(self) -> None:
        """Should catch APIError with status code."""
        result = runner.invoke(_app, ["raises-api-error"])
        assert result.exit_code == 1
        assert "API_ERROR" in result.stderr
        assert "500" in result.stderr

    def test_catches_validation_error_exit_code_2(self) -> None:
        """ValidationError should exit with code 2."""
        result = runner.invoke(_app, ["raises-validation-error"])
        assert result.exit_code == 2
        assert "INVALID_INPUT" in result.stderr
        assert "email" in result.stderr

    def test_respects_custom_exit_code(self) -> None:
        """Should respect custom exit_code from MonarchCLIError."""
        result = runner.invoke(_app, ["raises-custom-exit-code"])
        assert result.exit_code == 42


class TestHandleErrorsUnexpected:
    """Tests for unexpected exception handling."""

    def test_wraps_unexpected_error(self) -> None:
        """Should wrap unexpected exceptions in MonarchCLIError."""
        result = runner.invoke(_app, ["raises-unexpected"])
        assert result.exit_code == 1
        assert "Unexpected error" in result.stderr
        assert "something went wrong" in result.stderr

    def test_unexpected_error_has_error_structure(self) -> None:
        """Unexpected errors should still have structured output."""
        result = runner.invoke(_app, ["raises-unexpected"])
        assert '"error": true' in result.stderr
        assert '"code":' in result.stderr

    def test_debug_shows_traceback(self) -> None:
        """Should show traceback when debug mode is enabled."""
        with mock.patch("monarch_cli.core.error_handler.is_debug", return_value=True):
            result = runner.invoke(_app, ["raises-unexpected"])

        assert result.exit_code == 1
        # Traceback should be in stderr
        assert "Traceback" in result.stderr or "ValueError" in result.stderr

    def test_non_debug_hides_traceback(self) -> None:
        """Should hide traceback when debug mode is disabled."""
        with mock.patch("monarch_cli.core.error_handler.is_debug", return_value=False):
            result = runner.invoke(_app, ["raises-unexpected"])

        assert result.exit_code == 1
        # Should not have full traceback
        assert "Traceback (most recent call last)" not in result.stderr


class TestHandleErrorsKeyboardInterrupt:
    """Tests for KeyboardInterrupt handling."""

    def test_keyboard_interrupt_exits_130(self) -> None:
        """Should exit with code 130 on KeyboardInterrupt."""
        result = runner.invoke(_app, ["raises-keyboard-interrupt"])
        assert result.exit_code == 130

    def test_keyboard_interrupt_message(self) -> None:
        """Should print 'Interrupted.' message."""
        result = runner.invoke(_app, ["raises-keyboard-interrupt"])
        assert "Interrupted" in result.stderr

    def test_keyboard_interrupt_no_json(self) -> None:
        """KeyboardInterrupt should not output JSON error structure."""
        result = runner.invoke(_app, ["raises-keyboard-interrupt"])
        assert '"error":' not in result.stderr


class TestHandleErrorsDecorator:
    """Tests for decorator behavior."""

    def test_preserves_function_name(self) -> None:
        """Decorator should preserve function name via functools.wraps."""

        @handle_errors
        def my_function() -> None:
            pass

        assert my_function.__name__ == "my_function"

    def test_preserves_docstring(self) -> None:
        """Decorator should preserve docstring via functools.wraps."""

        @handle_errors
        def my_function() -> None:
            """My docstring."""
            pass

        assert my_function.__doc__ == "My docstring."
