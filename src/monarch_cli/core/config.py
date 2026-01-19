"""Layered configuration system for monarch-cli.

Configuration is loaded with the following precedence (highest wins):
1. CLI flags (runtime overrides)
2. Environment variables
3. Config file (~/.config/monarch-cli/config.toml)
4. Built-in defaults

This follows the standard CLI convention used by git, kubectl, docker, etc.
"""

from __future__ import annotations

import os
import sys
import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import platformdirs

if TYPE_CHECKING:
    from typing import Any

# Valid format options
FormatType = Literal["json", "table", "csv", "compact", "plain"]
VALID_FORMATS: tuple[FormatType, ...] = ("json", "table", "csv", "compact", "plain")

# Default values
DEFAULT_FORMAT: FormatType = "plain"
DEFAULT_TIMEOUT_SECONDS: int = 30
DEFAULT_MAX_RETRIES: int = 3


def get_config_dir() -> Path:
    """Get the config directory, respecting MONARCH_CONFIG_DIR env var.

    Creates the directory if it doesn't exist.

    Returns:
        Path to config directory (created if needed).
    """
    env_dir = os.environ.get("MONARCH_CONFIG_DIR")
    config_dir = Path(env_dir) if env_dir else Path(platformdirs.user_config_dir("monarch-cli"))
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def get_config_file_path() -> Path:
    """Get the path to the config file.

    Returns:
        Path to config.toml (may not exist).
    """
    return get_config_dir() / "config.toml"


@dataclass(frozen=True)
class Config:
    """Application configuration with layered loading.

    Attributes:
        format: Default output format (json, table, csv, compact, plain)
        color: Whether to use colored output
        verbose: Enable verbose logging
        debug: Enable debug mode (stack traces, implies verbose)
        quiet: Quiet mode - output only IDs
        timeout_seconds: Request timeout in seconds
        max_retries: Number of retry attempts for failed requests
        confirm_destructive: Require confirmation for destructive operations
    """

    format: FormatType = DEFAULT_FORMAT
    color: bool = True
    verbose: bool = False
    debug: bool = False
    quiet: bool = False
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    max_retries: int = DEFAULT_MAX_RETRIES
    confirm_destructive: bool = True

    # Track which source set each value (for debugging/diagnostics)
    _sources: dict[str, str] = field(default_factory=dict, compare=False, repr=False)

    @classmethod
    def load(cls) -> Config:
        """Load configuration from all sources with proper precedence.

        Precedence (highest to lowest):
        1. Environment variables
        2. Config file (~/.config/monarch-cli/config.toml)
        3. Built-in defaults

        Note: CLI flags are applied separately via with_overrides().
        """
        sources: dict[str, str] = {}

        # Start with defaults
        config_dict: dict[str, Any] = {
            "format": DEFAULT_FORMAT,
            "color": True,
            "verbose": False,
            "debug": False,
            "quiet": False,
            "timeout_seconds": DEFAULT_TIMEOUT_SECONDS,
            "max_retries": DEFAULT_MAX_RETRIES,
            "confirm_destructive": True,
        }
        for key in config_dict:
            sources[key] = "default"

        # Layer 1: Config file
        file_config = _load_config_file()
        for key, value in file_config.items():
            if key in config_dict:
                config_dict[key] = value
                sources[key] = "file"

        # Layer 2: Environment variables
        env_config = _load_from_env()
        for key, value in env_config.items():
            if value is not None:
                config_dict[key] = value
                sources[key] = "env"

        return cls(**config_dict, _sources=sources)

    def with_overrides(
        self,
        *,
        format: FormatType | None = None,
        color: bool | None = None,
        verbose: bool | None = None,
        debug: bool | None = None,
        quiet: bool | None = None,
        timeout_seconds: int | None = None,
        max_retries: int | None = None,
        confirm_destructive: bool | None = None,
    ) -> Config:
        """Create a new Config with specified overrides applied.

        This is used to apply CLI flags on top of the loaded config.

        Args:
            format: Override output format
            color: Override color setting
            verbose: Override verbose setting
            debug: Override debug setting
            quiet: Override quiet setting
            timeout_seconds: Override timeout
            max_retries: Override max retries
            confirm_destructive: Override confirmation setting

        Returns:
            New Config instance with overrides applied.
        """
        new_sources = dict(self._sources)
        overrides: dict[str, Any] = {}

        if format is not None:
            overrides["format"] = format
            new_sources["format"] = "cli"
        if color is not None:
            overrides["color"] = color
            new_sources["color"] = "cli"
        if verbose is not None:
            overrides["verbose"] = verbose
            new_sources["verbose"] = "cli"
        if debug is not None:
            overrides["debug"] = debug
            new_sources["debug"] = "cli"
        if quiet is not None:
            overrides["quiet"] = quiet
            new_sources["quiet"] = "cli"
        if timeout_seconds is not None:
            overrides["timeout_seconds"] = timeout_seconds
            new_sources["timeout_seconds"] = "cli"
        if max_retries is not None:
            overrides["max_retries"] = max_retries
            new_sources["max_retries"] = "cli"
        if confirm_destructive is not None:
            overrides["confirm_destructive"] = confirm_destructive
            new_sources["confirm_destructive"] = "cli"

        if not overrides:
            return self

        return replace(self, **overrides, _sources=new_sources)

    def get_source(self, key: str) -> str:
        """Get the source that set a config value.

        Args:
            key: Config key to check.

        Returns:
            Source name: 'default', 'file', 'env', or 'cli'
        """
        return self._sources.get(key, "unknown")

    def is_verbose(self) -> bool:
        """Check if verbose output is enabled.

        Debug mode implies verbose.
        """
        return self.verbose or self.debug


def _load_config_file() -> dict[str, Any]:
    """Load configuration from TOML file.

    Returns:
        Dict of config values from file, empty if file doesn't exist or is invalid.
    """
    config_path = get_config_file_path()
    if not config_path.exists():
        return {}

    try:
        with config_path.open("rb") as f:
            data = tomllib.load(f)
    except (tomllib.TOMLDecodeError, OSError):
        # Invalid TOML or read error - silently use defaults
        return {}

    result: dict[str, Any] = {}

    # Parse format
    if "format" in data:
        fmt = _parse_format(data["format"])
        if fmt is not None:
            result["format"] = fmt

    # Parse color
    if "color" in data and isinstance(data["color"], bool):
        result["color"] = data["color"]

    # Parse verbose
    if "verbose" in data and isinstance(data["verbose"], bool):
        result["verbose"] = data["verbose"]

    # Parse debug
    if "debug" in data and isinstance(data["debug"], bool):
        result["debug"] = data["debug"]

    # Parse quiet
    if "quiet" in data and isinstance(data["quiet"], bool):
        result["quiet"] = data["quiet"]

    # Parse timeout
    if "timeout" in data:
        timeout = _parse_positive_int(data["timeout"])
        if timeout is not None:
            result["timeout_seconds"] = timeout

    # Parse max_retries
    if "max_retries" in data:
        retries = _parse_positive_int(data["max_retries"])
        if retries is not None:
            result["max_retries"] = retries

    # Parse confirm_destructive
    if "confirm_destructive" in data and isinstance(data["confirm_destructive"], bool):
        result["confirm_destructive"] = data["confirm_destructive"]

    return result


def _load_from_env() -> dict[str, Any | None]:
    """Load configuration from environment variables.

    Returns:
        Dict of config values from env vars (None for unset).
    """
    result: dict[str, Any | None] = {}

    # MONARCH_FORMAT
    env_format = os.environ.get("MONARCH_FORMAT")
    if env_format:
        result["format"] = _parse_format(env_format)

    # MONARCH_VERBOSE
    env_verbose = os.environ.get("MONARCH_VERBOSE")
    if env_verbose:
        result["verbose"] = _parse_bool(env_verbose)

    # MONARCH_DEBUG
    env_debug = os.environ.get("MONARCH_DEBUG")
    if env_debug:
        result["debug"] = _parse_bool(env_debug)

    # MONARCH_QUIET
    env_quiet = os.environ.get("MONARCH_QUIET")
    if env_quiet:
        result["quiet"] = _parse_bool(env_quiet)

    # MONARCH_TIMEOUT
    env_timeout = os.environ.get("MONARCH_TIMEOUT")
    if env_timeout:
        timeout = _parse_positive_int(env_timeout)
        if timeout is not None:
            result["timeout_seconds"] = timeout

    # MONARCH_MAX_RETRIES
    env_retries = os.environ.get("MONARCH_MAX_RETRIES")
    if env_retries:
        retries = _parse_positive_int(env_retries)
        if retries is not None:
            result["max_retries"] = retries

    # Color: NO_COLOR standard + MONARCH_NO_COLOR
    result["color"] = _parse_color_from_env()

    return result


def _parse_format(value: Any) -> FormatType | None:
    """Parse format from config value.

    Args:
        value: Value to parse (string expected).

    Returns:
        Valid format or None if invalid.
    """
    if not isinstance(value, str):
        return None
    value_lower = value.lower().strip()
    if value_lower in VALID_FORMATS:
        return value_lower  # type: ignore[return-value]
    return None


def _parse_bool(value: str) -> bool:
    """Parse boolean from string (truthy: '1', 'true', 'yes')."""
    return value.lower().strip() in ("1", "true", "yes")


def _parse_positive_int(value: Any) -> int | None:
    """Parse positive integer from value.

    Args:
        value: Value to parse.

    Returns:
        Positive integer or None if invalid/non-positive.
    """
    try:
        if isinstance(value, str):
            parsed = int(value.strip())
        elif isinstance(value, int):
            parsed = value
        else:
            return None
        return parsed if parsed > 0 else None
    except ValueError:
        return None


def _parse_color_from_env() -> bool | None:
    """Parse color setting from environment variables.

    Color is disabled if:
    - NO_COLOR is set (any non-empty value, per no-color.org standard)
    - MONARCH_NO_COLOR=1/true/yes is set

    Returns:
        False if color should be disabled, None if no env var set.
    """
    # NO_COLOR standard: any non-empty value disables color
    if os.environ.get("NO_COLOR"):
        return False

    # MONARCH_NO_COLOR: truthy value disables color
    monarch_no_color = os.environ.get("MONARCH_NO_COLOR")
    if monarch_no_color and _parse_bool(monarch_no_color):
        return False

    # No color-related env vars set
    return None


# Global cached config instance
_config: Config | None = None


def get_config() -> Config:
    """Get the global Config instance.

    Loads configuration on first call, returns cached instance on subsequent calls.
    Use set_config() to update after applying CLI overrides.
    """
    global _config  # noqa: PLW0603
    if _config is None:
        _config = Config.load()
    return _config


def set_config(config: Config) -> None:
    """Set the global Config instance.

    Used to apply CLI flag overrides to the loaded config.

    Args:
        config: Config instance to set as global.
    """
    global _config  # noqa: PLW0603
    _config = config


def reset_config() -> None:
    """Reset the cached config (useful for testing)."""
    global _config  # noqa: PLW0603
    _config = None


def init_config_file() -> Path:
    """Create a default config file if it doesn't exist.

    Returns:
        Path to the config file.
    """
    config_dir = get_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)

    config_path = get_config_file_path()
    if not config_path.exists():
        config_path.write_text(DEFAULT_CONFIG_TEMPLATE)

    return config_path


DEFAULT_CONFIG_TEMPLATE = """\
# Monarch CLI Configuration
# https://github.com/crcatala/monarch-cli
#
# This file sets default values. They can be overridden by:
# - Environment variables (MONARCH_*)
# - CLI flags (--verbose, --json, etc.)

# Output format: plain, json, table, csv, compact
# "plain" shows human-friendly output with emoji icons (TTY default)
# "json" is used automatically when output is piped
format = "plain"

# Enable colored output (respects NO_COLOR env var)
color = true

# Show operational progress messages
verbose = false

# Show stack traces on errors (implies verbose)
debug = false

# Output only IDs, one per line (for scripting)
quiet = false

# API request timeout in seconds
timeout = 30

# Number of retry attempts for transient failures
max_retries = 3

# Require confirmation for destructive operations (delete, etc.)
confirm_destructive = true
"""
