"""Tests for output module."""

from __future__ import annotations

import json
from datetime import date, datetime

import pytest

from monarch_cli.core.exceptions import APIError, AuthenticationError, MonarchCLIError
from monarch_cli.output import (
    OutputFormat,
    is_verbose,
    output,
    output_error,
    set_verbose,
)


class TestOutputFormat:
    """Tests for OutputFormat enum."""

    def test_json_value(self) -> None:
        """JSON format should have 'json' value."""
        assert OutputFormat.JSON.value == "json"

    def test_compact_value(self) -> None:
        """Compact format should have 'compact' value."""
        assert OutputFormat.COMPACT.value == "compact"

    def test_table_value(self) -> None:
        """Table format should have 'table' value."""
        assert OutputFormat.TABLE.value == "table"

    def test_csv_value(self) -> None:
        """CSV format should have 'csv' value."""
        assert OutputFormat.CSV.value == "csv"

    def test_is_string_enum(self) -> None:
        """OutputFormat should be a string enum for Typer compatibility."""
        assert isinstance(OutputFormat.JSON, str)
        assert OutputFormat.JSON == "json"


class TestOutput:
    """Tests for output function."""

    def test_json_format_indented(self, capsys: pytest.CaptureFixture[str]) -> None:
        """JSON format should be indented with 2 spaces."""
        data = {"key": "value", "nested": {"a": 1}}
        output(data, OutputFormat.JSON)
        captured = capsys.readouterr()

        assert json.loads(captured.out) == data
        # Should have newlines (indented)
        assert "\n" in captured.out
        # Should have 2-space indentation
        assert '  "' in captured.out

    def test_compact_format_single_line(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Compact format should be single line without indentation."""
        data = {"key": "value", "nested": {"a": 1}}
        output(data, OutputFormat.COMPACT)
        captured = capsys.readouterr()

        assert json.loads(captured.out) == data
        # Should be single line (no newlines except trailing)
        assert "\n" not in captured.out.strip()

    def test_default_format_is_json(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Default format should be JSON (indented)."""
        data = {"key": "value"}
        output(data)  # No format specified
        captured = capsys.readouterr()

        assert json.loads(captured.out) == data
        assert "\n" in captured.out  # Indented

    def test_table_falls_back_to_json(self, capsys: pytest.CaptureFixture[str]) -> None:
        """TABLE format should fall back to JSON in Phase 1."""
        data = {"key": "value"}
        output(data, OutputFormat.TABLE)
        captured = capsys.readouterr()

        assert json.loads(captured.out) == data
        assert "\n" in captured.out  # Indented like JSON

    def test_csv_falls_back_to_json(self, capsys: pytest.CaptureFixture[str]) -> None:
        """CSV format should fall back to JSON in Phase 1."""
        data = {"key": "value"}
        output(data, OutputFormat.CSV)
        captured = capsys.readouterr()

        assert json.loads(captured.out) == data

    def test_outputs_to_stdout(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Output should go to stdout, not stderr."""
        data = {"test": True}
        output(data)
        captured = capsys.readouterr()

        assert captured.out != ""
        assert captured.err == ""

    def test_handles_list(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Should handle list data."""
        data = [{"id": 1}, {"id": 2}]
        output(data)
        captured = capsys.readouterr()

        assert json.loads(captured.out) == data

    def test_handles_empty_dict(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Should handle empty dict."""
        data: dict[str, str] = {}
        output(data)
        captured = capsys.readouterr()

        assert json.loads(captured.out) == data

    def test_handles_none_values(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Should handle None values in data."""
        data = {"key": None}
        output(data)
        captured = capsys.readouterr()

        result = json.loads(captured.out)
        assert result["key"] is None


class TestOutputNonSerializable:
    """Tests for handling non-JSON-serializable objects."""

    def test_handles_date(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Should handle date objects via default=str."""
        data = {"date": date(2026, 1, 18)}
        output(data)
        captured = capsys.readouterr()

        result = json.loads(captured.out)
        assert result["date"] == "2026-01-18"

    def test_handles_datetime(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Should handle datetime objects via default=str."""
        data = {"datetime": datetime(2026, 1, 18, 10, 30, 0)}
        output(data)
        captured = capsys.readouterr()

        result = json.loads(captured.out)
        assert "2026-01-18" in result["datetime"]

    def test_handles_custom_object(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Should handle custom objects via default=str."""

        class CustomObj:
            def __str__(self) -> str:
                return "custom_string"

        data = {"obj": CustomObj()}
        output(data)
        captured = capsys.readouterr()

        result = json.loads(captured.out)
        assert result["obj"] == "custom_string"


class TestOutputError:
    """Tests for output_error function."""

    def test_outputs_to_stderr(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Should output to stderr, not stdout."""
        error = AuthenticationError()
        output_error(error)
        captured = capsys.readouterr()

        assert captured.out == ""
        assert captured.err != ""

    def test_json_structure(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Should output valid JSON with expected structure."""
        error = AuthenticationError()
        output_error(error)
        captured = capsys.readouterr()

        data = json.loads(captured.err)
        assert data["error"] is True
        assert data["code"] == "AUTH_REQUIRED"
        assert "message" in data
        assert "details" in data

    def test_includes_message(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Should include error message."""
        error = MonarchCLIError("Custom error message")
        output_error(error)
        captured = capsys.readouterr()

        data = json.loads(captured.err)
        assert data["message"] == "Custom error message"

    def test_includes_details(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Should include error details."""
        error = APIError("API failed", status_code=503)
        output_error(error)
        captured = capsys.readouterr()

        data = json.loads(captured.err)
        assert data["details"]["status_code"] == 503

    def test_is_indented(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Error output should be indented for readability."""
        error = AuthenticationError()
        output_error(error)
        captured = capsys.readouterr()

        # Should have newlines (indented)
        assert "\n" in captured.err


class TestVerboseFlag:
    """Tests for verbose flag functions."""

    def test_default_not_verbose(self) -> None:
        """Should default to not verbose."""
        set_verbose(False)  # Reset to known state
        assert is_verbose() is False

    def test_set_verbose_true(self) -> None:
        """Should be able to enable verbose mode."""
        set_verbose(True)
        assert is_verbose() is True
        set_verbose(False)  # Cleanup

    def test_set_verbose_false(self) -> None:
        """Should be able to disable verbose mode."""
        set_verbose(True)
        set_verbose(False)
        assert is_verbose() is False

    def test_toggle_verbose(self) -> None:
        """Should be able to toggle verbose mode."""
        set_verbose(False)
        assert is_verbose() is False

        set_verbose(True)
        assert is_verbose() is True

        set_verbose(False)
        assert is_verbose() is False
