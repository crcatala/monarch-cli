"""Tests for plain text output formatter."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from monarch_cli.output import (
    OutputFormat,
    get_default_format,
    output,
    set_default_format,
)
from monarch_cli.output.plain import (
    _format_field_name,
    _format_value,
    _get_icon,
    format_plain,
    format_plain_item,
    should_use_color,
)


class TestShouldUseColor:
    """Tests for should_use_color function."""

    def test_no_color_env_set_empty(self) -> None:
        """NO_COLOR set to empty string should disable color."""
        with patch.dict(os.environ, {"NO_COLOR": ""}, clear=False):
            assert should_use_color() is False

    def test_no_color_env_set_value(self) -> None:
        """NO_COLOR set to any value should disable color."""
        with patch.dict(os.environ, {"NO_COLOR": "1"}, clear=False):
            assert should_use_color() is False

    def test_term_dumb_disables_color(self) -> None:
        """TERM=dumb should disable color."""
        # Build clean env with TERM=dumb, no NO_COLOR
        env_copy = dict(os.environ)
        env_copy.pop("NO_COLOR", None)
        env_copy["TERM"] = "dumb"
        with (
            patch("sys.stdout.isatty", return_value=True),
            patch.dict(os.environ, env_copy, clear=True),
        ):
            assert should_use_color() is False

    def test_not_tty_disables_color(self) -> None:
        """Non-TTY stdout should disable color."""
        # Clear NO_COLOR and set normal TERM
        env_copy = dict(os.environ)
        env_copy.pop("NO_COLOR", None)
        env_copy["TERM"] = "xterm-256color"
        with (
            patch("sys.stdout.isatty", return_value=False),
            patch.dict(os.environ, env_copy, clear=True),
        ):
            assert should_use_color() is False

    def test_tty_enables_color(self) -> None:
        """TTY stdout with no blockers should enable color."""
        # Clear NO_COLOR and set normal TERM
        env_copy = dict(os.environ)
        env_copy.pop("NO_COLOR", None)
        env_copy["TERM"] = "xterm-256color"
        with (
            patch("sys.stdout.isatty", return_value=True),
            patch.dict(os.environ, env_copy, clear=True),
        ):
            assert should_use_color() is True


class TestFormatValue:
    """Tests for _format_value helper."""

    def test_none_returns_empty(self) -> None:
        """None should return empty string."""
        assert _format_value(None) == ""

    def test_bool_true(self) -> None:
        """True should return 'Yes'."""
        assert _format_value(True) == "Yes"

    def test_bool_false(self) -> None:
        """False should return 'No'."""
        assert _format_value(False) == "No"

    def test_float_formats_as_currency(self) -> None:
        """Floats should format with 2 decimal places and commas."""
        assert _format_value(1234.5) == "1,234.50"
        assert _format_value(0.99) == "0.99"

    def test_list_joins_with_commas(self) -> None:
        """Lists should join with commas."""
        assert _format_value(["a", "b", "c"]) == "a, b, c"

    def test_dict_formats_key_value(self) -> None:
        """Dicts should format as key: value pairs."""
        result = _format_value({"a": 1, "b": 2})
        assert "a: 1" in result
        assert "b: 2" in result

    def test_string_passthrough(self) -> None:
        """Strings should pass through."""
        assert _format_value("hello") == "hello"

    def test_int_converts_to_string(self) -> None:
        """Integers should convert to string."""
        assert _format_value(42) == "42"


class TestGetIcon:
    """Tests for _get_icon helper."""

    def test_known_field_id(self) -> None:
        """id field should get bookmark icon."""
        assert _get_icon("id") == "🔖"

    def test_known_field_name(self) -> None:
        """name field should get pin icon."""
        assert _get_icon("name") == "📌"

    def test_known_field_balance(self) -> None:
        """balance field should get money bag icon."""
        assert _get_icon("balance") == "💰"

    def test_camel_case_variant(self) -> None:
        """camelCase variants should also work."""
        assert _get_icon("currentBalance") == "💰"
        assert _get_icon("institutionName") == "🏦"

    def test_snake_case_variant(self) -> None:
        """snake_case variants should also work."""
        assert _get_icon("current_balance") == "💰"
        assert _get_icon("institution_name") == "🏦"

    def test_unknown_field(self) -> None:
        """Unknown fields should get default bullet."""
        assert _get_icon("unknown_field") == "•"
        assert _get_icon("random") == "•"


class TestFormatFieldName:
    """Tests for _format_field_name helper."""

    def test_snake_case(self) -> None:
        """snake_case should convert to Title Case."""
        assert _format_field_name("current_balance") == "Current Balance"

    def test_camel_case(self) -> None:
        """camelCase should convert to Title Case."""
        assert _format_field_name("currentBalance") == "Current Balance"

    def test_simple_word(self) -> None:
        """Simple word should title case."""
        assert _format_field_name("name") == "Name"
        assert _format_field_name("id") == "Id"


class TestFormatPlainItem:
    """Tests for format_plain_item function."""

    def test_simple_item(self) -> None:
        """Should format simple item with icons."""
        item = {"id": "123", "name": "Test"}
        result = format_plain_item(item, use_color=False)

        assert "🔖" in result  # id icon
        assert "Id: 123" in result
        assert "📌" in result  # name icon
        assert "Name: Test" in result

    def test_skips_none_values(self) -> None:
        """Should skip None values."""
        item = {"id": "123", "name": None}
        result = format_plain_item(item, use_color=False)

        assert "123" in result
        assert "Name:" not in result

    def test_skips_empty_string_values(self) -> None:
        """Should skip empty string values."""
        item = {"id": "123", "name": ""}
        result = format_plain_item(item, use_color=False)

        assert "123" in result
        assert "Name:" not in result

    def test_with_color_includes_ansi(self) -> None:
        """With color enabled, should include ANSI codes."""
        item = {"id": "123"}
        result = format_plain_item(item, use_color=True)

        assert "\033[1m" in result  # Bold
        assert "\033[0m" in result  # Reset

    def test_without_color_no_ansi(self) -> None:
        """Without color, should not include ANSI codes."""
        item = {"id": "123"}
        result = format_plain_item(item, use_color=False)

        assert "\033[" not in result


class TestFormatPlain:
    """Tests for format_plain function."""

    def test_single_dict(self) -> None:
        """Should format single dict."""
        data = {"id": "123", "name": "Test"}
        result = format_plain(data, use_color=False)

        assert "Id: 123" in result
        assert "Name: Test" in result

    def test_list_of_dicts_with_separator(self) -> None:
        """Should format list of dicts with separator."""
        data = [{"id": "1"}, {"id": "2"}]
        result = format_plain(data, use_color=False)

        assert "Id: 1" in result
        assert "Id: 2" in result
        assert "─" * 50 in result  # Separator

    def test_empty_list(self) -> None:
        """Empty list should return 'No results.'."""
        result = format_plain([], use_color=False)
        assert result == "No results."

    def test_list_of_scalars(self) -> None:
        """List of scalars should join with newlines."""
        data = ["a", "b", "c"]
        result = format_plain(data, use_color=False)
        assert result == "a\nb\nc"

    def test_scalar_value(self) -> None:
        """Scalar value should convert to string."""
        assert format_plain("hello", use_color=False) == "hello"
        assert format_plain(42, use_color=False) == "42"

    def test_auto_detects_color(self) -> None:
        """Should auto-detect color when use_color is None."""
        with patch("monarch_cli.output.plain.should_use_color", return_value=False):
            result = format_plain({"id": "123"})
            assert "\033[" not in result


class TestGetDefaultFormat:
    """Tests for get_default_format function."""

    def test_tty_returns_plain(self) -> None:
        """TTY stdout should return PLAIN format."""
        set_default_format(None)  # Clear any override
        with patch("sys.stdout.isatty", return_value=True):
            assert get_default_format() == OutputFormat.PLAIN

    def test_pipe_returns_json(self) -> None:
        """Piped stdout should return JSON format."""
        set_default_format(None)  # Clear any override
        with patch("sys.stdout.isatty", return_value=False):
            assert get_default_format() == OutputFormat.JSON

    def test_override_respected(self) -> None:
        """set_default_format override should be respected."""
        try:
            set_default_format(OutputFormat.JSON)
            with patch("sys.stdout.isatty", return_value=True):
                # Even though TTY, override says JSON
                assert get_default_format() == OutputFormat.JSON
        finally:
            set_default_format(None)  # Cleanup


class TestOutputWithPlain:
    """Tests for output() function with PLAIN format."""

    def test_output_plain_explicit(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Explicit PLAIN format should use plain formatter."""
        data = {"id": "123", "name": "Test"}
        output(data, OutputFormat.PLAIN)
        captured = capsys.readouterr()

        assert "Id: 123" in captured.out
        assert "Name: Test" in captured.out
        # Should not be JSON
        assert "{" not in captured.out

    def test_output_default_tty_uses_plain(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Default format in TTY should use PLAIN."""
        set_default_format(None)  # Clear override
        with (
            patch("sys.stdout.isatty", return_value=True),
            patch("monarch_cli.output.get_default_format", return_value=OutputFormat.PLAIN),
        ):
            data = {"id": "123"}
            output(data)
            captured = capsys.readouterr()
            # Output has color codes when TTY - check for emoji and value
            assert "🔖" in captured.out
            assert "123" in captured.out

    def test_output_default_pipe_uses_json(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Default format when piped should use JSON."""
        set_default_format(None)  # Clear override
        with (
            patch("sys.stdout.isatty", return_value=False),
            patch("monarch_cli.output.get_default_format", return_value=OutputFormat.JSON),
        ):
            data = {"id": "123"}
            output(data)
            captured = capsys.readouterr()
            assert '"id": "123"' in captured.out

    def test_plain_has_no_ansi_when_piped(self, capsys: pytest.CaptureFixture[str]) -> None:
        """PLAIN format should have no ANSI codes when not a TTY."""
        with patch("sys.stdout.isatty", return_value=False):
            data = {"id": "123"}
            output(data, OutputFormat.PLAIN)
            captured = capsys.readouterr()

            # Should not have ANSI escape codes
            assert "\033[" not in captured.out


class TestOutputFormatEnum:
    """Tests for OutputFormat enum with PLAIN."""

    def test_plain_value(self) -> None:
        """PLAIN format should have 'plain' value."""
        assert OutputFormat.PLAIN.value == "plain"

    def test_plain_is_string_enum(self) -> None:
        """PLAIN should be a string enum for Typer compatibility."""
        assert isinstance(OutputFormat.PLAIN, str)
        assert OutputFormat.PLAIN == "plain"
