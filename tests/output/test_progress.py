"""Tests for output/progress module."""

import sys
from unittest.mock import patch

import pytest

from monarch_cli.output.progress import is_interactive, spinner


class TestIsInteractive:
    """Tests for is_interactive()."""

    def test_returns_false_when_stderr_not_tty(self) -> None:
        """is_interactive returns False when stderr is not a TTY."""
        with patch.object(sys.stderr, "isatty", return_value=False):
            assert is_interactive() is False

    def test_returns_true_when_stderr_is_tty(self) -> None:
        """is_interactive returns True when stderr is a TTY."""
        with patch.object(sys.stderr, "isatty", return_value=True):
            assert is_interactive() is True


class TestSpinner:
    """Tests for spinner context manager."""

    def test_spinner_non_interactive_prints_message(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """In non-interactive mode, spinner just prints message to stderr."""
        with (
            patch.object(sys.stderr, "isatty", return_value=False),
            spinner("Test message..."),
        ):
            pass

        captured = capsys.readouterr()
        assert "Test message..." in captured.err
        assert captured.out == ""  # stdout should be empty

    def test_spinner_non_interactive_executes_block(self) -> None:
        """Spinner executes the context block in non-interactive mode."""
        executed = False
        with (
            patch.object(sys.stderr, "isatty", return_value=False),
            spinner("Loading..."),
        ):
            executed = True

        assert executed is True

    def test_spinner_interactive_executes_block(self) -> None:
        """Spinner executes the context block in interactive mode."""
        executed = False
        # Mock isatty but also need to handle Rich's console
        with (
            patch.object(sys.stderr, "isatty", return_value=True),
            spinner("Loading..."),
        ):
            executed = True

        assert executed is True

    def test_spinner_context_manager_yields(self) -> None:
        """Spinner yields control properly as a context manager."""
        result = None
        with (
            patch.object(sys.stderr, "isatty", return_value=False),
            spinner("Processing..."),
        ):
            result = 42

        assert result == 42

    def test_spinner_preserves_exception(self) -> None:
        """Spinner propagates exceptions from the context block."""
        with (
            patch.object(sys.stderr, "isatty", return_value=False),
            pytest.raises(ValueError, match="test error"),
            spinner("Failing..."),
        ):
            raise ValueError("test error")
