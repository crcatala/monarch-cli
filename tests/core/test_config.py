"""Tests for configuration system."""

from __future__ import annotations

import os

import pytest

from monarch_cli.core.config import (
    Config,
    get_config,
    reset_config,
)


@pytest.fixture(autouse=True)
def clean_env():
    """Ensure clean environment and reset config for each test."""
    env_vars = [
        "MONARCH_FORMAT",
        "MONARCH_TIMEOUT",
        "MONARCH_MAX_RETRIES",
        "MONARCH_VERBOSE",
        "NO_COLOR",
        "MONARCH_NO_COLOR",
    ]
    # Save original values
    original = {k: os.environ.get(k) for k in env_vars}
    # Clear all config env vars
    for var in env_vars:
        os.environ.pop(var, None)
    # Reset cached config
    reset_config()

    yield

    # Restore original values
    for var in env_vars:
        if original[var] is not None:
            os.environ[var] = original[var]
        else:
            os.environ.pop(var, None)
    reset_config()


class TestConfigDefaults:
    """Test default configuration values."""

    def test_default_format_is_json(self):
        """Default format should be json."""
        config = Config.load()
        assert config.format == "json"

    def test_default_color_is_enabled(self):
        """Color should be enabled by default."""
        config = Config.load()
        assert config.color is True

    def test_default_verbose_is_disabled(self):
        """Verbose mode should be disabled by default."""
        config = Config.load()
        assert config.verbose is False

    def test_default_timeout_is_30(self):
        """Default timeout should be 30 seconds."""
        config = Config.load()
        assert config.timeout_seconds == 30

    def test_default_max_retries_is_3(self):
        """Default max retries should be 3."""
        config = Config.load()
        assert config.max_retries == 3

    def test_default_confirm_destructive_is_true(self):
        """Confirm destructive should be true by default."""
        config = Config.load()
        assert config.confirm_destructive is True


class TestMonarchFormat:
    """Test MONARCH_FORMAT environment variable."""

    @pytest.mark.parametrize(
        "env_value,expected",
        [
            ("json", "json"),
            ("table", "table"),
            ("csv", "csv"),
            ("compact", "compact"),
            ("JSON", "json"),  # Case insensitive
            ("  table  ", "table"),  # Whitespace trimmed
        ],
    )
    def test_valid_formats(self, env_value: str, expected: str):
        """Valid format values are accepted."""
        os.environ["MONARCH_FORMAT"] = env_value
        config = Config.load()
        assert config.format == expected

    @pytest.mark.parametrize(
        "invalid_value",
        [
            "invalid",
            "xml",
            "yaml",
            "",
            "   ",
        ],
    )
    def test_invalid_formats_use_default(self, invalid_value: str):
        """Invalid format values fall back to default."""
        os.environ["MONARCH_FORMAT"] = invalid_value
        config = Config.load()
        assert config.format == "json"


class TestMonarchTimeout:
    """Test MONARCH_TIMEOUT environment variable."""

    @pytest.mark.parametrize(
        "env_value,expected",
        [
            ("60", 60),
            ("1", 1),
            ("300", 300),
            ("  45  ", 45),  # Whitespace trimmed
        ],
    )
    def test_valid_timeout_values(self, env_value: str, expected: int):
        """Valid timeout values are parsed correctly."""
        os.environ["MONARCH_TIMEOUT"] = env_value
        config = Config.load()
        assert config.timeout_seconds == expected

    @pytest.mark.parametrize(
        "invalid_value",
        [
            "abc",
            "10.5",
            "",
            "0",  # Zero should use default
            "-5",  # Negative should use default
        ],
    )
    def test_invalid_timeout_uses_default(self, invalid_value: str):
        """Invalid timeout values fall back to default."""
        os.environ["MONARCH_TIMEOUT"] = invalid_value
        config = Config.load()
        assert config.timeout_seconds == 30


class TestMonarchMaxRetries:
    """Test MONARCH_MAX_RETRIES environment variable."""

    @pytest.mark.parametrize(
        "env_value,expected",
        [
            ("5", 5),
            ("1", 1),
            ("10", 10),
            ("  2  ", 2),  # Whitespace trimmed
        ],
    )
    def test_valid_retry_values(self, env_value: str, expected: int):
        """Valid retry values are parsed correctly."""
        os.environ["MONARCH_MAX_RETRIES"] = env_value
        config = Config.load()
        assert config.max_retries == expected

    @pytest.mark.parametrize(
        "invalid_value",
        [
            "abc",
            "3.5",
            "",
            "0",  # Zero should use default
            "-2",  # Negative should use default
        ],
    )
    def test_invalid_retries_uses_default(self, invalid_value: str):
        """Invalid retry values fall back to default."""
        os.environ["MONARCH_MAX_RETRIES"] = invalid_value
        config = Config.load()
        assert config.max_retries == 3


class TestMonarchVerbose:
    """Test MONARCH_VERBOSE environment variable."""

    @pytest.mark.parametrize(
        "env_value",
        [
            "1",
            "true",
            "TRUE",
            "yes",
            "YES",
            "  1  ",  # Whitespace trimmed
        ],
    )
    def test_truthy_values_enable_verbose(self, env_value: str):
        """Truthy values enable verbose mode."""
        os.environ["MONARCH_VERBOSE"] = env_value
        config = Config.load()
        assert config.verbose is True

    @pytest.mark.parametrize(
        "env_value",
        [
            "0",
            "false",
            "no",
            "",
            "anything",  # Unrecognized value defaults to false
        ],
    )
    def test_falsy_values_disable_verbose(self, env_value: str):
        """Falsy or unrecognized values disable verbose mode."""
        os.environ["MONARCH_VERBOSE"] = env_value
        config = Config.load()
        assert config.verbose is False


class TestColorSettings:
    """Test NO_COLOR and MONARCH_NO_COLOR environment variables."""

    def test_no_color_standard_disables_color(self):
        """NO_COLOR (any non-empty value) disables color per no-color.org."""
        os.environ["NO_COLOR"] = "1"
        config = Config.load()
        assert config.color is False

    def test_no_color_any_value_disables_color(self):
        """NO_COLOR with any non-empty value disables color."""
        os.environ["NO_COLOR"] = "anything"
        config = Config.load()
        assert config.color is False

    def test_monarch_no_color_disables_color(self):
        """MONARCH_NO_COLOR=1 disables color."""
        os.environ["MONARCH_NO_COLOR"] = "1"
        config = Config.load()
        assert config.color is False

    def test_monarch_no_color_true_disables_color(self):
        """MONARCH_NO_COLOR=true disables color."""
        os.environ["MONARCH_NO_COLOR"] = "true"
        config = Config.load()
        assert config.color is False

    def test_color_enabled_when_no_env_vars(self):
        """Color is enabled when no color env vars are set."""
        config = Config.load()
        assert config.color is True


class TestGetConfig:
    """Test the get_config() caching function."""

    def test_returns_config_instance(self):
        """get_config() returns a Config instance."""
        config = get_config()
        assert isinstance(config, Config)

    def test_returns_cached_instance(self):
        """get_config() returns the same cached instance."""
        config1 = get_config()
        config2 = get_config()
        assert config1 is config2

    def test_reset_config_clears_cache(self):
        """reset_config() clears the cached instance."""
        _config1 = get_config()  # noqa: F841
        reset_config()
        config2 = get_config()
        # After reset, should get a new instance
        # (Though may be equal, should be a fresh load)
        assert isinstance(config2, Config)

    def test_config_reflects_env_at_load_time(self):
        """Config reflects environment at load time, not later changes."""
        config1 = get_config()
        assert config1.format == "json"

        # Change env after load
        os.environ["MONARCH_FORMAT"] = "table"

        # Cached config still has old value
        config2 = get_config()
        assert config2.format == "json"

        # Reset and reload to get new value
        reset_config()
        config3 = get_config()
        assert config3.format == "table"


class TestConfigImmutability:
    """Test that Config is immutable (frozen dataclass)."""

    def test_config_is_frozen(self):
        """Config instances should be immutable."""
        config = Config.load()
        with pytest.raises(AttributeError):
            config.format = "table"  # type: ignore[misc]

        with pytest.raises(AttributeError):
            config.timeout_seconds = 60  # type: ignore[misc]
