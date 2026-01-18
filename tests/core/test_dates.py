"""Tests for monarch_cli.core.dates module."""

from __future__ import annotations

from datetime import date
from unittest import mock

from monarch_cli.core.dates import DatePreset, parse_date_range, resolve_preset


class TestDatePreset:
    """Tests for DatePreset enum."""

    def test_all_presets_are_strings(self) -> None:
        """All presets should have string values."""
        for preset in DatePreset:
            assert isinstance(preset.value, str)

    def test_expected_presets_exist(self) -> None:
        """All expected presets should exist."""
        expected = [
            "today",
            "yesterday",
            "this-week",
            "last-week",
            "this-month",
            "last-month",
            "last-30-days",
            "last-90-days",
            "this-year",
            "last-year",
            "ytd",
            "all",
        ]
        actual = [p.value for p in DatePreset]
        for preset in expected:
            assert preset in actual

    def test_preset_count(self) -> None:
        """Should have exactly 12 presets."""
        assert len(list(DatePreset)) == 12


class TestResolvePreset:
    """Tests for resolve_preset function."""

    @mock.patch("monarch_cli.core.dates.date")
    def test_today(self, mock_date: mock.MagicMock) -> None:
        """TODAY should return current date for both start and end."""
        mock_date.today.return_value = date(2026, 1, 18)
        start, end = resolve_preset(DatePreset.TODAY)
        assert start == date(2026, 1, 18)
        assert end == date(2026, 1, 18)

    @mock.patch("monarch_cli.core.dates.date")
    def test_yesterday(self, mock_date: mock.MagicMock) -> None:
        """YESTERDAY should return previous day."""
        mock_date.today.return_value = date(2026, 1, 18)
        start, end = resolve_preset(DatePreset.YESTERDAY)
        assert start == date(2026, 1, 17)
        assert end == date(2026, 1, 17)

    @mock.patch("monarch_cli.core.dates.date")
    def test_this_week_monday(self, mock_date: mock.MagicMock) -> None:
        """THIS_WEEK should start on Monday."""
        # Saturday Jan 18, 2026
        mock_date.today.return_value = date(2026, 1, 18)
        start, end = resolve_preset(DatePreset.THIS_WEEK)
        # Monday of that week is Jan 12
        assert start == date(2026, 1, 12)
        assert end == date(2026, 1, 18)

    @mock.patch("monarch_cli.core.dates.date")
    def test_this_week_on_monday(self, mock_date: mock.MagicMock) -> None:
        """THIS_WEEK when today is Monday should start today."""
        # Monday Jan 12, 2026
        mock_date.today.return_value = date(2026, 1, 12)
        start, end = resolve_preset(DatePreset.THIS_WEEK)
        assert start == date(2026, 1, 12)
        assert end == date(2026, 1, 12)

    @mock.patch("monarch_cli.core.dates.date")
    def test_last_week(self, mock_date: mock.MagicMock) -> None:
        """LAST_WEEK should return Monday-Sunday of previous week."""
        # Saturday Jan 18, 2026
        mock_date.today.return_value = date(2026, 1, 18)
        start, end = resolve_preset(DatePreset.LAST_WEEK)
        # Previous week: Mon Jan 5 - Sun Jan 11
        assert start == date(2026, 1, 5)
        assert end == date(2026, 1, 11)

    @mock.patch("monarch_cli.core.dates.date")
    def test_this_month(self, mock_date: mock.MagicMock) -> None:
        """THIS_MONTH should start on first of month."""
        mock_date.today.return_value = date(2026, 1, 18)
        start, end = resolve_preset(DatePreset.THIS_MONTH)
        assert start == date(2026, 1, 1)
        assert end == date(2026, 1, 18)

    @mock.patch("monarch_cli.core.dates.date")
    def test_last_month(self, mock_date: mock.MagicMock) -> None:
        """LAST_MONTH should return previous month's full range."""
        mock_date.today.return_value = date(2026, 1, 18)
        start, end = resolve_preset(DatePreset.LAST_MONTH)
        assert start == date(2025, 12, 1)
        assert end == date(2025, 12, 31)

    @mock.patch("monarch_cli.core.dates.date")
    def test_last_month_february(self, mock_date: mock.MagicMock) -> None:
        """LAST_MONTH in March should handle February correctly."""
        mock_date.today.return_value = date(2026, 3, 15)
        start, end = resolve_preset(DatePreset.LAST_MONTH)
        assert start == date(2026, 2, 1)
        assert end == date(2026, 2, 28)  # 2026 is not a leap year

    @mock.patch("monarch_cli.core.dates.date")
    def test_last_30_days(self, mock_date: mock.MagicMock) -> None:
        """LAST_30_DAYS should go back exactly 30 days."""
        mock_date.today.return_value = date(2026, 1, 18)
        start, end = resolve_preset(DatePreset.LAST_30_DAYS)
        assert start == date(2025, 12, 19)
        assert end == date(2026, 1, 18)

    @mock.patch("monarch_cli.core.dates.date")
    def test_last_90_days(self, mock_date: mock.MagicMock) -> None:
        """LAST_90_DAYS should go back exactly 90 days."""
        mock_date.today.return_value = date(2026, 1, 18)
        start, end = resolve_preset(DatePreset.LAST_90_DAYS)
        assert start == date(2025, 10, 20)
        assert end == date(2026, 1, 18)

    @mock.patch("monarch_cli.core.dates.date")
    def test_this_year(self, mock_date: mock.MagicMock) -> None:
        """THIS_YEAR should start on Jan 1."""
        mock_date.today.return_value = date(2026, 6, 15)
        start, end = resolve_preset(DatePreset.THIS_YEAR)
        assert start == date(2026, 1, 1)
        assert end == date(2026, 6, 15)

    @mock.patch("monarch_cli.core.dates.date")
    def test_ytd_alias(self, mock_date: mock.MagicMock) -> None:
        """YTD should be alias for THIS_YEAR."""
        mock_date.today.return_value = date(2026, 6, 15)
        ytd_start, ytd_end = resolve_preset(DatePreset.YTD)
        this_year_start, this_year_end = resolve_preset(DatePreset.THIS_YEAR)
        assert ytd_start == this_year_start
        assert ytd_end == this_year_end

    @mock.patch("monarch_cli.core.dates.date")
    def test_last_year(self, mock_date: mock.MagicMock) -> None:
        """LAST_YEAR should return full previous year."""
        mock_date.today.return_value = date(2026, 6, 15)
        # date() constructor is called, need to make it return real dates
        mock_date.side_effect = lambda *args, **kwargs: date(*args, **kwargs)
        start, end = resolve_preset(DatePreset.LAST_YEAR)
        assert start == date(2025, 1, 1)
        assert end == date(2025, 12, 31)

    def test_all_returns_none(self) -> None:
        """ALL should return (None, None) for no filtering."""
        start, end = resolve_preset(DatePreset.ALL)
        assert start is None
        assert end is None


class TestParseDateRange:
    """Tests for parse_date_range function."""

    @mock.patch("monarch_cli.core.dates.date")
    def test_preset_only(self, mock_date: mock.MagicMock) -> None:
        """Should resolve preset to ISO strings."""
        mock_date.today.return_value = date(2026, 1, 18)
        start, end = parse_date_range(DatePreset.TODAY)
        assert start == "2026-01-18"
        assert end == "2026-01-18"

    def test_all_preset_returns_none(self) -> None:
        """ALL preset should return (None, None)."""
        start, end = parse_date_range(DatePreset.ALL)
        assert start is None
        assert end is None

    @mock.patch("monarch_cli.core.dates.date")
    def test_explicit_start_overrides_preset(self, mock_date: mock.MagicMock) -> None:
        """Explicit start should override preset start."""
        mock_date.today.return_value = date(2026, 1, 18)
        start, end = parse_date_range(
            preset=DatePreset.THIS_MONTH,
            start=date(2026, 1, 10),
        )
        assert start == "2026-01-10"  # Explicit
        assert end == "2026-01-18"  # From preset

    @mock.patch("monarch_cli.core.dates.date")
    def test_explicit_end_overrides_preset(self, mock_date: mock.MagicMock) -> None:
        """Explicit end should override preset end."""
        mock_date.today.return_value = date(2026, 1, 18)
        start, end = parse_date_range(
            preset=DatePreset.THIS_MONTH,
            end=date(2026, 1, 15),
        )
        assert start == "2026-01-01"  # From preset
        assert end == "2026-01-15"  # Explicit

    def test_explicit_dates_only(self) -> None:
        """Should work with explicit dates and no preset."""
        start, end = parse_date_range(
            start=date(2026, 1, 1),
            end=date(2026, 1, 31),
        )
        assert start == "2026-01-01"
        assert end == "2026-01-31"

    def test_no_arguments_returns_none(self) -> None:
        """Should return (None, None) with no arguments."""
        start, end = parse_date_range()
        assert start is None
        assert end is None

    def test_iso_format(self) -> None:
        """Should return dates in YYYY-MM-DD format."""
        start, end = parse_date_range(
            start=date(2026, 1, 5),
            end=date(2026, 12, 25),
        )
        # Verify format (10 chars, dashes in right places)
        assert len(start) == 10
        assert start[4] == "-"
        assert start[7] == "-"
        assert len(end) == 10
