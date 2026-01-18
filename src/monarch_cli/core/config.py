"""Configuration system for monarch-cli.

Reads configuration from environment variables with sensible defaults.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

# Valid format options
FormatType = Literal["json", "table", "csv", "compact"]
VALID_FORMATS: tuple[FormatType, ...] = ("json", "table", "csv", "compact")

# Default values
DEFAULT_FORMAT: FormatType = "json"
DEFAULT_TIMEOUT_SECONDS: int = 30
DEFAULT_MAX_RETRIES: int = 3


@dataclass(frozen=True)
class Config:
    """Application configuration loaded from environment variables.

    Attributes:
        format: Default output format (json, table, csv, compact)
        color: Whether to use colored output
        verbose: Enable verbose logging
        timeout_seconds: Request timeout in seconds
        max_retries: Number of retry attempts for failed requests
        confirm_destructive: Require confirmation for destructive operations
    """

    format: FormatType
    color: bool
    verbose: bool
    timeout_seconds: int
    max_retries: int
    confirm_destructive: bool

    @classmethod
    def load(cls) -> Config:
        """Load configuration from environment variables.

        Environment Variables:
            MONARCH_FORMAT: Output format (json, table, csv, compact)
            MONARCH_TIMEOUT: Request timeout in seconds
            MONARCH_MAX_RETRIES: Number of retry attempts
            MONARCH_VERBOSE: Enable verbose mode (1 to enable)
            NO_COLOR: Disable colored output (standard convention)
            MONARCH_NO_COLOR: Disable colored output (project-specific)

        Invalid values are ignored and defaults are used.
        """
        return cls(
            format=_parse_format(os.environ.get("MONARCH_FORMAT")),
            color=_parse_color(),
            verbose=_parse_bool(os.environ.get("MONARCH_VERBOSE")),
            timeout_seconds=_parse_int(os.environ.get("MONARCH_TIMEOUT"), DEFAULT_TIMEOUT_SECONDS),
            max_retries=_parse_int(os.environ.get("MONARCH_MAX_RETRIES"), DEFAULT_MAX_RETRIES),
            confirm_destructive=True,  # Default to requiring confirmation
        )


def _parse_format(value: str | None) -> FormatType:
    """Parse format from environment variable."""
    if value is None:
        return DEFAULT_FORMAT
    value_lower = value.lower().strip()
    if value_lower in VALID_FORMATS:
        return value_lower  # type: ignore[return-value]
    return DEFAULT_FORMAT


def _parse_bool(value: str | None) -> bool:
    """Parse boolean from environment variable (truthy: '1', 'true', 'yes')."""
    if value is None:
        return False
    return value.lower().strip() in ("1", "true", "yes")


def _parse_int(value: str | None, default: int) -> int:
    """Parse integer from environment variable, returning default on invalid input."""
    if value is None:
        return default
    try:
        parsed = int(value.strip())
        # Ensure positive values for timeout and retries
        return parsed if parsed > 0 else default
    except ValueError:
        return default


def _parse_color() -> bool:
    """Parse color setting from environment variables.

    Color is enabled by default, disabled if:
    - NO_COLOR is set (any non-empty value, per no-color.org standard)
    - MONARCH_NO_COLOR=1 is set
    """
    # NO_COLOR standard: any non-empty value disables color
    if os.environ.get("NO_COLOR"):
        return False
    # Project-specific override
    return not _parse_bool(os.environ.get("MONARCH_NO_COLOR"))


# Global cached config instance
_config: Config | None = None


def get_config() -> Config:
    """Get the cached global Config instance.

    Loads configuration on first call, returns cached instance on subsequent calls.
    """
    global _config  # noqa: PLW0603
    if _config is None:
        _config = Config.load()
    return _config


def reset_config() -> None:
    """Reset the cached config (useful for testing)."""
    global _config  # noqa: PLW0603
    _config = None
