"""Plain text output formatter for monarch-cli.

Human-friendly output with emoji icons and labeled fields.
Designed for terminal display while remaining parseable.
"""

from __future__ import annotations

import os
import sys
from typing import Any

# Module-level color override (set by --no-color flag)
_color_enabled: bool | None = None


def set_color_enabled(enabled: bool | None) -> None:
    """Override color detection.

    Args:
        enabled: True to force color, False to disable, None for auto-detect.
    """
    global _color_enabled
    _color_enabled = enabled


def should_use_color() -> bool:
    """Check if colored output should be used.

    Returns False when:
    - set_color_enabled(False) was called (--no-color flag)
    - NO_COLOR environment variable is set (any value)
    - TERM=dumb
    - stdout is not a TTY (piped/redirected)

    See: https://no-color.org/
    """
    # Explicit override from --no-color flag takes precedence
    if _color_enabled is not None:
        return _color_enabled

    # NO_COLOR takes precedence (any value means no color)
    if os.environ.get("NO_COLOR") is not None:
        return False

    # TERM=dumb means no color support
    if os.environ.get("TERM") == "dumb":
        return False

    # If not a TTY, don't use color
    return sys.stdout.isatty()


def _format_value(value: Any) -> str:
    """Format a single value for display.

    Args:
        value: Any value to format.

    Returns:
        String representation of the value.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, float):
        # Format as currency if it looks like money
        return f"{value:,.2f}"
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    if isinstance(value, dict):
        # Nested dict - show key: value pairs
        parts = [f"{k}: {_format_value(v)}" for k, v in value.items()]
        return ", ".join(parts)
    return str(value)


# Mapping of common field names to emoji icons
_FIELD_ICONS: dict[str, str] = {
    # Identity fields
    "id": "🔖",
    "name": "📌",
    "displayName": "📌",
    "display_name": "📌",
    # Account fields
    "balance": "💰",
    "currentBalance": "💰",
    "current_balance": "💰",
    "availableBalance": "💳",
    "available_balance": "💳",
    "institution": "🏦",
    "institutionName": "🏦",
    "institution_name": "🏦",
    "accountType": "📋",
    "account_type": "📋",
    "type": "📋",
    # Transaction fields
    "amount": "💵",
    "date": "📅",
    "transactionDate": "📅",
    "transaction_date": "📅",
    "description": "📝",
    "merchant": "🏪",
    "merchantName": "🏪",
    "merchant_name": "🏪",
    "category": "🏷️",
    "categoryName": "🏷️",
    "category_name": "🏷️",
    "pending": "⏳",
    "isPending": "⏳",
    "is_pending": "⏳",
    # Budget fields
    "budgeted": "📊",
    "budgetAmount": "📊",
    "budget_amount": "📊",
    "spent": "💸",
    "spentAmount": "💸",
    "spent_amount": "💸",
    "remaining": "✨",
    "remainingAmount": "✨",
    "remaining_amount": "✨",
    # Cashflow fields
    "income": "📈",
    "expense": "📉",
    "expenses": "📉",
    "net": "📊",
    "savings": "🏦",
    # Category fields
    "group": "📁",
    "icon": "🎨",
    # Status fields
    "status": "🔄",
    "error": "❌",
    "message": "💬",
    # Other common fields
    "email": "📧",
    "created": "🕐",
    "updated": "🕐",
    "createdAt": "🕐",
    "created_at": "🕐",
    "updatedAt": "🕐",
    "updated_at": "🕐",
}

# Default icon for unknown fields
_DEFAULT_ICON = "•"


def _get_icon(field: str) -> str:
    """Get emoji icon for a field name.

    Args:
        field: Field name to look up.

    Returns:
        Emoji icon or default bullet.
    """
    return _FIELD_ICONS.get(field, _DEFAULT_ICON)


def _format_field_name(field: str) -> str:
    """Format a field name for display.

    Converts snake_case and camelCase to Title Case.

    Args:
        field: Field name to format.

    Returns:
        Human-readable field name.
    """
    # Handle camelCase
    result = ""
    for i, char in enumerate(field):
        if char.isupper() and i > 0:
            result += " "
        result += char

    # Handle snake_case and capitalize
    return result.replace("_", " ").title()


def format_plain_item(item: dict[str, Any], use_color: bool = True) -> str:
    """Format a single item as plain text with emoji icons.

    Args:
        item: Dictionary to format.
        use_color: Whether to use ANSI colors (for field names).

    Returns:
        Formatted string with labeled fields.
    """
    lines = []

    for field, value in item.items():
        if value is None or value == "":
            continue

        icon = _get_icon(field)
        label = _format_field_name(field)
        formatted_value = _format_value(value)

        # Add color to label if enabled
        if use_color:
            lines.append(f"{icon} \033[1m{label}:\033[0m {formatted_value}")
        else:
            lines.append(f"{icon} {label}: {formatted_value}")

    return "\n".join(lines)


def format_plain(data: Any, use_color: bool | None = None) -> str:
    """Format data as human-friendly plain text.

    Args:
        data: Data to format (dict, list of dicts, or scalar).
        use_color: Whether to use ANSI colors. If None, auto-detect.

    Returns:
        Formatted string ready for terminal display.

    Example output:
        🔖 Id: acc_123abc
        📌 Name: Chase Checking
        💰 Balance: 1234.56
        🏦 Institution: Chase

        ──────────────────────────────────────────────────

        🔖 Id: acc_456def
        📌 Name: Savings Account
        ...
    """
    if use_color is None:
        use_color = should_use_color()

    # Separator between items
    separator = "\n\n" + "─" * 50 + "\n\n"

    if isinstance(data, list):
        if not data:
            return "No results."

        if isinstance(data[0], dict):
            # List of dicts - format each with separator
            formatted_items = [format_plain_item(item, use_color) for item in data]
            return separator.join(formatted_items)
        else:
            # List of scalars
            return "\n".join(str(item) for item in data)

    elif isinstance(data, dict):
        return format_plain_item(data, use_color)

    else:
        # Scalar value
        return str(data)
