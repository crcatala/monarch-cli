"""Tests for layered configuration system."""

from __future__ import annotations

import os

import pytest

from monarch_cli.core.config import (
    Config,
    get_config,
    get_config_dir,
    get_config_file_path,
    reset_config,
    set_config,
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    """Ensure clean environment and reset config for each test."""
    env_vars = [
        "MONARCH_FORMAT",
        "MONARCH_TIMEOUT",
        "MONARCH_MAX_RETRIES",
        "MONARCH_VERBOSE",
        "MONARCH_DEBUG",
        "MONARCH_QUIET",
        "NO_COLOR",
        "MONARCH_NO_COLOR",
        "MONARCH_CONFIG_DIR",
    ]
    # Clear all config env vars
    for var in env_vars:
        monkeypatch.delenv(var, raising=False)

    # Use temp dir for config to avoid reading user's actual config
    monkeypatch.setenv("MONARCH_CONFIG_DIR", str(tmp_path))

    # Reset cached config
    reset_config()

    yield

    reset_config()


class TestConfigDefaults:
    """Test default configuration values."""

    def test_default_format_is_plain(self):
        """Default format should be plain (human-friendly for TTY)."""
        config = Config.load()
        assert config.format == "plain"

    def test_default_color_is_enabled(self):
        """Color should be enabled by default."""
        config = Config.load()
        assert config.color is True

    def test_default_verbose_is_disabled(self):
        """Verbose mode should be disabled by default."""
        config = Config.load()
        assert config.verbose is False

    def test_default_debug_is_disabled(self):
        """Debug mode should be disabled by default."""
        config = Config.load()
        assert config.debug is False

    def test_default_quiet_is_disabled(self):
        """Quiet mode should be disabled by default."""
        config = Config.load()
        assert config.quiet is False

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
            ("plain", "plain"),
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
        """Invalid format values fall back to default (plain)."""
        os.environ["MONARCH_FORMAT"] = invalid_value
        config = Config.load()
        assert config.format == "plain"


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
        assert isinstance(config2, Config)

    def test_config_reflects_env_at_load_time(self):
        """Config reflects environment at load time, not later changes."""
        config1 = get_config()
        assert config1.format == "plain"

        # Change env after load
        os.environ["MONARCH_FORMAT"] = "table"

        # Cached config still has old value
        config2 = get_config()
        assert config2.format == "plain"

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


class TestConfigFile:
    """Test configuration file loading."""

    def test_loads_from_toml_file(self, tmp_path):
        """Config loads values from TOML file."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("""
format = "table"
timeout = 60
max_retries = 5
verbose = true
color = false
""")
        os.environ["MONARCH_CONFIG_DIR"] = str(tmp_path)
        reset_config()
        config = Config.load()

        assert config.format == "table"
        assert config.timeout_seconds == 60
        assert config.max_retries == 5
        assert config.verbose is True
        assert config.color is False

    def test_env_overrides_file(self, tmp_path):
        """Environment variables override config file values."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("""
format = "table"
timeout = 60
""")
        os.environ["MONARCH_CONFIG_DIR"] = str(tmp_path)
        os.environ["MONARCH_FORMAT"] = "csv"
        reset_config()
        config = Config.load()

        # ENV should override file
        assert config.format == "csv"
        # File value should be used for timeout (no env override)
        assert config.timeout_seconds == 60

    def test_invalid_toml_uses_defaults(self, tmp_path):
        """Invalid TOML file is ignored, defaults are used."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("this is not valid toml [[[")
        os.environ["MONARCH_CONFIG_DIR"] = str(tmp_path)
        reset_config()
        config = Config.load()

        assert config.format == "plain"
        assert config.timeout_seconds == 30

    def test_missing_file_uses_defaults(self, tmp_path):
        """Missing config file is fine, defaults are used."""
        os.environ["MONARCH_CONFIG_DIR"] = str(tmp_path)
        reset_config()
        config = Config.load()

        assert config.format == "plain"
        assert config.timeout_seconds == 30

    def test_partial_config_file(self, tmp_path):
        """Partial config file only overrides specified values."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("""
# Only set timeout
timeout = 120
""")
        os.environ["MONARCH_CONFIG_DIR"] = str(tmp_path)
        reset_config()
        config = Config.load()

        assert config.timeout_seconds == 120
        # Other values should be defaults
        assert config.format == "plain"
        assert config.max_retries == 3


class TestConfigWithOverrides:
    """Test Config.with_overrides() method."""

    def test_with_overrides_creates_new_config(self):
        """with_overrides returns a new Config instance."""
        config1 = Config.load()
        config2 = config1.with_overrides(verbose=True)

        assert config1 is not config2
        assert config1.verbose is False
        assert config2.verbose is True

    def test_with_overrides_preserves_other_values(self):
        """with_overrides preserves non-overridden values."""
        config1 = Config.load()
        config2 = config1.with_overrides(format="json")

        assert config2.format == "json"
        # Other values unchanged
        assert config2.timeout_seconds == config1.timeout_seconds
        assert config2.max_retries == config1.max_retries
        assert config2.color == config1.color

    def test_with_overrides_none_is_ignored(self):
        """with_overrides ignores None values."""
        config1 = Config.load()
        config2 = config1.with_overrides(verbose=None, format=None)

        assert config1 is config2  # Same instance returned when no changes

    def test_with_overrides_tracks_source(self):
        """with_overrides tracks source as 'cli'."""
        config = Config.load()
        config = config.with_overrides(verbose=True, format="json")

        assert config.get_source("verbose") == "cli"
        assert config.get_source("format") == "cli"
        # Non-overridden values keep original source
        assert config.get_source("timeout_seconds") == "default"


class TestSetConfig:
    """Test set_config() function."""

    def test_set_config_updates_global(self):
        """set_config() updates the global config instance."""
        config1 = Config.load()
        config2 = config1.with_overrides(verbose=True)
        set_config(config2)

        assert get_config() is config2
        assert get_config().verbose is True


class TestConfigSourceTracking:
    """Test that config tracks where values came from."""

    def test_default_source(self):
        """Default values are tracked as 'default'."""
        config = Config.load()
        assert config.get_source("format") == "default"
        assert config.get_source("timeout_seconds") == "default"

    def test_file_source(self, tmp_path):
        """File values are tracked as 'file'."""
        config_file = tmp_path / "config.toml"
        config_file.write_text('format = "table"')
        os.environ["MONARCH_CONFIG_DIR"] = str(tmp_path)
        reset_config()
        config = Config.load()

        assert config.get_source("format") == "file"
        assert config.get_source("timeout_seconds") == "default"

    def test_env_source(self):
        """Env values are tracked as 'env'."""
        os.environ["MONARCH_FORMAT"] = "csv"
        config = Config.load()

        assert config.get_source("format") == "env"

    def test_cli_source(self):
        """CLI overrides are tracked as 'cli'."""
        config = Config.load().with_overrides(format="json")
        assert config.get_source("format") == "cli"


class TestIsVerbose:
    """Test is_verbose() helper method."""

    def test_verbose_true(self):
        """is_verbose returns True when verbose is True."""
        config = Config.load().with_overrides(verbose=True)
        assert config.is_verbose() is True

    def test_debug_implies_verbose(self):
        """is_verbose returns True when debug is True."""
        config = Config.load().with_overrides(debug=True)
        assert config.is_verbose() is True

    def test_both_false(self):
        """is_verbose returns False when both verbose and debug are False."""
        config = Config.load()
        assert config.is_verbose() is False


class TestConfigDir:
    """Test config directory functions."""

    def test_get_config_dir_respects_env(self, tmp_path):
        """get_config_dir respects MONARCH_CONFIG_DIR."""
        custom_dir = tmp_path / "custom"
        os.environ["MONARCH_CONFIG_DIR"] = str(custom_dir)
        assert get_config_dir() == custom_dir

    def test_get_config_file_path(self, tmp_path):
        """get_config_file_path returns config.toml in config dir."""
        os.environ["MONARCH_CONFIG_DIR"] = str(tmp_path)
        assert get_config_file_path() == tmp_path / "config.toml"
