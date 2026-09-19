"""Tests for output module."""

from __future__ import annotations

import json
from datetime import date, datetime

import pytest

from monarch_cli.core.exceptions import APIError, AuthenticationError, MonarchCLIError
from monarch_cli.output import (
    OutputFormat,
    is_quiet,
    is_verbose,
    output,
    output_error,
    set_quiet,
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


class TestQuietFlag:
    """Tests for quiet flag functions."""

    def test_default_not_quiet(self) -> None:
        """Should default to not quiet."""
        set_quiet(False)  # Reset to known state
        assert is_quiet() is False

    def test_set_quiet_true(self) -> None:
        """Should be able to enable quiet mode."""
        set_quiet(True)
        assert is_quiet() is True
        set_quiet(False)  # Cleanup

    def test_set_quiet_false(self) -> None:
        """Should be able to disable quiet mode."""
        set_quiet(True)
        set_quiet(False)
        assert is_quiet() is False


class TestQuietModeOutput:
    """Tests for quiet mode output."""

    def test_quiet_list_outputs_ids_only(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Quiet mode with list of dicts outputs only IDs."""
        data = [{"id": "ACC123", "name": "Checking"}, {"id": "ACC456", "name": "Savings"}]
        output(data, quiet=True)
        captured = capsys.readouterr()

        lines = captured.out.strip().split("\n")
        assert lines == ["ACC123", "ACC456"]

    def test_quiet_single_dict_outputs_id(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Quiet mode with single dict outputs only the ID."""
        data = {"id": "ACC123", "name": "Checking", "balance": 1234.56}
        output(data, quiet=True)
        captured = capsys.readouterr()

        assert captured.out.strip() == "ACC123"

    def test_quiet_custom_id_field(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Quiet mode respects custom id_field parameter."""
        data = [{"transaction_id": "TXN001"}, {"transaction_id": "TXN002"}]
        output(data, quiet=True, id_field="transaction_id")
        captured = capsys.readouterr()

        lines = captured.out.strip().split("\n")
        assert lines == ["TXN001", "TXN002"]

    def test_quiet_empty_list_no_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Quiet mode with empty list produces no output."""
        data: list[dict[str, str]] = []
        output(data, quiet=True)
        captured = capsys.readouterr()

        assert captured.out == ""

    def test_quiet_dict_missing_id_field_errors(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Quiet mode with a record missing the id field errors, never silent."""
        from monarch_cli.core.exceptions import ValidationError

        data = {"name": "Test", "value": 123}
        with pytest.raises(ValidationError) as exc_info:
            output(data, quiet=True)
        assert exc_info.value.code.value == "INVALID_INPUT"
        assert capsys.readouterr().out == ""

    def test_quiet_list_record_missing_id_errors(self, capsys: pytest.CaptureFixture[str]) -> None:
        """A list record without an ID errors instead of printing the dict."""
        from monarch_cli.core.exceptions import ValidationError

        data = [{"id": "ACC1"}, {"name": "no-id"}]
        with pytest.raises(ValidationError):
            output(data, quiet=True)
        assert capsys.readouterr().out == "ACC1\n"

    def test_quiet_empty_dict_no_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        """An empty collection produces no output and no error."""
        output([], quiet=True)
        assert capsys.readouterr().out == ""

    def test_quiet_list_of_scalars(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Quiet mode with list of scalars outputs each item."""
        data = ["item1", "item2", "item3"]
        output(data, quiet=True)
        captured = capsys.readouterr()

        lines = captured.out.strip().split("\n")
        assert lines == ["item1", "item2", "item3"]

    def test_quiet_overrides_format(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Quiet mode takes precedence over format parameter."""
        data = [{"id": "ACC123", "name": "Checking"}]
        output(data, format=OutputFormat.JSON, quiet=True)
        captured = capsys.readouterr()

        # Should be just the ID, not JSON
        assert captured.out.strip() == "ACC123"

    def test_quiet_uses_module_flag_when_not_specified(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Quiet mode uses module flag when quiet parameter not specified."""
        data = [{"id": "ACC123"}]

        # With module flag set
        set_quiet(True)
        output(data)
        captured = capsys.readouterr()
        assert captured.out.strip() == "ACC123"

        # Reset
        set_quiet(False)

    def test_quiet_parameter_overrides_module_flag(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Explicit quiet=False overrides module quiet flag."""
        data = [{"id": "ACC123", "name": "Test"}]

        set_quiet(True)
        output(data, quiet=False)  # Explicit False
        captured = capsys.readouterr()
        set_quiet(False)  # Cleanup

        # Should output JSON, not just ID
        result = json.loads(captured.out)
        assert result == data


class TestDisplayFieldProjection:
    """Concise-format field selection (owner attribution and liability display).

    ``display_fields`` restricts plain, table, and compact output to the
    ordered field selection. Machine-readable formats (JSON, CSV, NDJSON)
    always keep the complete normalized record, and ``--raw`` is never
    projected.
    """

    DATA = [
        {"id": "a1", "name": "Checking", "owner_id": "u1", "owner_name": "Alex", "balance": 5},
        {"id": "a2", "name": "Savings", "owner_id": None, "owner_name": None, "balance": 7},
    ]

    FIELDS = ("id", "name", "owner_name")

    def test_plain_projects_to_display_fields(self, capsys: pytest.CaptureFixture[str]) -> None:
        output(self.DATA, OutputFormat.PLAIN, display_fields=self.FIELDS)
        captured = capsys.readouterr()
        assert "Owner Name: Alex" in captured.out
        assert "owner_id" not in captured.out
        assert "Balance" not in captured.out

    def test_table_projects_to_display_fields(self, capsys: pytest.CaptureFixture[str]) -> None:
        output(self.DATA, OutputFormat.TABLE, display_fields=self.FIELDS)
        captured = capsys.readouterr()
        assert "owner_name" in captured.out
        assert "balance" not in captured.out

    def test_json_keeps_complete_record(self, capsys: pytest.CaptureFixture[str]) -> None:
        output(self.DATA, OutputFormat.JSON, display_fields=self.FIELDS)
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert result[0] == self.DATA[0]
        assert result[1] == self.DATA[1]

    def test_compact_projects_to_display_fields(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Compact is a concise single-line summary view, like plain/table."""
        output(self.DATA, OutputFormat.COMPACT, display_fields=self.FIELDS)
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert result[0] == {"id": "a1", "name": "Checking", "owner_name": "Alex"}
        assert result[1] == {"id": "a2", "name": "Savings", "owner_name": None}

    def test_csv_keeps_complete_record(self, capsys: pytest.CaptureFixture[str]) -> None:
        output(self.DATA, OutputFormat.CSV, display_fields=self.FIELDS)
        captured = capsys.readouterr()
        assert "owner_id" in captured.out
        assert "balance" in captured.out

    def test_none_selection_is_identity(self, capsys: pytest.CaptureFixture[str]) -> None:
        output(self.DATA, OutputFormat.PLAIN, display_fields=None)
        captured = capsys.readouterr()
        assert "Balance: 5" in captured.out

    def test_non_dict_entries_pass_through(self, capsys: pytest.CaptureFixture[str]) -> None:
        output(["scalar"], OutputFormat.PLAIN, display_fields=self.FIELDS)
        captured = capsys.readouterr()
        assert "scalar" in captured.out
