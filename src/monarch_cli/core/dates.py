"""Date utilities and presets for filtering transactions and reports."""

from __future__ import annotations

import re
from datetime import date, timedelta
from enum import StrEnum

from .exceptions import ValidationError

#: Strict ``YYYY-MM-DD`` shape. ``date.fromisoformat`` alone also accepts
#: compact ISO forms (for example ``20240115``) on Python 3.11+, which the
#: documented CLI contract does not accept.
_ISO_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_iso_date(value: str | None, *, field: str) -> date | None:
    """Parse a strict ``YYYY-MM-DD`` date string into a :class:`date`.

    Shared parsing helper for every command that accepts an explicit date
    option. Validation failures raise the structured usage
    :class:`~monarch_cli.core.exceptions.ValidationError` (exit code 2) so
    bad input never reaches an authenticated API call.

    Args:
        value: Raw date string in ``YYYY-MM-DD`` format, or ``None``.
        field: CLI option name (without dashes) used in error messages and
            structured error details.

    Returns:
        The parsed date, or ``None`` when the input is ``None``.

    Raises:
        ValidationError: If the value is not a valid ``YYYY-MM-DD`` date.
    """
    if value is None:
        return None
    if not isinstance(value, str) or not _ISO_DATE_PATTERN.match(value):
        raise ValidationError(
            message=f"Invalid date format for --{field}: '{value}'. Use YYYY-MM-DD format.",
            field=field,
        )
    try:
        return date.fromisoformat(value)
    except ValueError as e:
        raise ValidationError(
            message=f"Invalid date for --{field}: '{value}'. Use YYYY-MM-DD format.",
            field=field,
        ) from e


def validate_date_ordering(
    start: date | None,
    end: date | None,
    *,
    start_field: str = "start",
    end_field: str = "end",
) -> None:
    """Reject an inverted explicit date range.

    Args:
        start: Parsed start date, or ``None`` (one-sided ranges are checked
            by the caller where the API requires both bounds).
        end: Parsed end date, or ``None``.
        start_field: CLI option name for error messages.
        end_field: CLI option name for error messages.

    Raises:
        ValidationError: If both bounds are present and ``start`` is after
            ``end``.
    """
    if start is not None and end is not None and start > end:
        raise ValidationError(
            message=(
                f"--{start_field} ({start.isoformat()}) must not be after "
                f"--{end_field} ({end.isoformat()})."
            ),
            field=start_field,
            details={
                start_field: start.isoformat(),
                end_field: end.isoformat(),
            },
        )


class DatePreset(StrEnum):
    """Common date range presets for financial reporting."""

    TODAY = "today"
    YESTERDAY = "yesterday"
    THIS_WEEK = "this-week"
    LAST_WEEK = "last-week"
    THIS_MONTH = "this-month"
    LAST_MONTH = "last-month"
    LAST_30_DAYS = "last-30-days"
    LAST_90_DAYS = "last-90-days"
    THIS_YEAR = "this-year"
    LAST_YEAR = "last-year"
    YTD = "ytd"
    ALL = "all"


def resolve_preset(preset: DatePreset) -> tuple[date | None, date | None]:
    """
    Resolve a date preset to a (start, end) date range.

    Args:
        preset: A DatePreset enum value.

    Returns:
        A tuple of (start_date, end_date). Either or both may be None.
        - ALL returns (None, None) meaning no date filter.
        - Other presets return concrete date bounds.
    """
    today = date.today()

    match preset:
        case DatePreset.TODAY:
            return (today, today)

        case DatePreset.YESTERDAY:
            yesterday = today - timedelta(days=1)
            return (yesterday, yesterday)

        case DatePreset.THIS_WEEK:
            # Monday = 0, so subtract weekday() to get to Monday
            start = today - timedelta(days=today.weekday())
            return (start, today)

        case DatePreset.LAST_WEEK:
            # Go to Monday of current week, then back 7 days
            this_monday = today - timedelta(days=today.weekday())
            last_monday = this_monday - timedelta(days=7)
            last_sunday = this_monday - timedelta(days=1)
            return (last_monday, last_sunday)

        case DatePreset.THIS_MONTH:
            start = today.replace(day=1)
            return (start, today)

        case DatePreset.LAST_MONTH:
            # First day of current month
            first_of_this_month = today.replace(day=1)
            # Last day of previous month
            last_of_prev_month = first_of_this_month - timedelta(days=1)
            # First day of previous month
            first_of_prev_month = last_of_prev_month.replace(day=1)
            return (first_of_prev_month, last_of_prev_month)

        case DatePreset.LAST_30_DAYS:
            start = today - timedelta(days=30)
            return (start, today)

        case DatePreset.LAST_90_DAYS:
            start = today - timedelta(days=90)
            return (start, today)

        case DatePreset.THIS_YEAR | DatePreset.YTD:
            # YTD is alias for THIS_YEAR
            start = today.replace(month=1, day=1)
            return (start, today)

        case DatePreset.LAST_YEAR:
            last_year = today.year - 1
            start = date(last_year, 1, 1)
            end = date(last_year, 12, 31)
            return (start, end)

        case DatePreset.ALL:
            return (None, None)


def parse_date_range(
    preset: DatePreset | None = None,
    start: date | None = None,
    end: date | None = None,
) -> tuple[str | None, str | None]:
    """
    Parse date range from preset and/or explicit dates.

    Explicit start/end dates take precedence over preset.

    Args:
        preset: Optional date preset for common ranges.
        start: Optional explicit start date (takes precedence over preset).
        end: Optional explicit end date (takes precedence over preset).

    Returns:
        A tuple of (start_date, end_date) as ISO format strings (YYYY-MM-DD),
        or None if no date filter should be applied for that bound.

    Examples:
        >>> parse_date_range(DatePreset.TODAY)
        ('2026-01-18', '2026-01-18')

        >>> parse_date_range(DatePreset.ALL)
        (None, None)

        >>> parse_date_range(DatePreset.THIS_MONTH, start=date(2026, 1, 10))
        ('2026-01-10', '2026-01-18')  # start overrides preset
    """
    # Start with preset resolution if provided
    if preset is not None:
        preset_start, preset_end = resolve_preset(preset)
    else:
        preset_start, preset_end = None, None

    # Explicit dates take precedence
    final_start = start if start is not None else preset_start
    final_end = end if end is not None else preset_end

    # Convert to ISO format strings
    start_str = final_start.isoformat() if final_start is not None else None
    end_str = final_end.isoformat() if final_end is not None else None

    return (start_str, end_str)
