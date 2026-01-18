---
id: mc-7fda
status: open
deps: [mc-299b]
links: []
created: 2026-01-18T16:06:48Z
type: task
priority: 1
assignee: cc-vps
parent: mc-beee
tags: [phase-3, config, core]
---
# Configuration System (Environment-Based)

Implement environment-based configuration system. TOML file support deferred to v1.1.

## Location
`src/monarch_cli/core/config.py`

## Environment Variables

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| MONARCH_TOKEN | string | - | Auth token (for CI/automation) |
| MONARCH_FORMAT | string | json | Default output format |
| MONARCH_TIMEOUT | int | 30 | Request timeout in seconds |
| MONARCH_MAX_RETRIES | int | 3 | Max retry attempts |
| MONARCH_VERBOSE | bool | false | Enable verbose output (1=true) |
| MONARCH_CONFIG_DIR | path | - | Override config directory |
| MONARCH_SESSION_PATH | path | - | Override session file path |
| NO_COLOR | any | - | Standard: disable colors if set |
| MONARCH_NO_COLOR | bool | - | CLI-specific: disable colors (1=true) |

## Implementation
```python
import os
from dataclasses import dataclass
from pathlib import Path
import platformdirs

from ..output import OutputFormat

def get_config_dir() -> Path:
    """Get config directory via platformdirs."""
    override = os.environ.get("MONARCH_CONFIG_DIR")
    if override:
        return Path(override)
    return Path(platformdirs.user_config_dir("monarch-cli"))

@dataclass
class Config:
    format: OutputFormat = OutputFormat.JSON
    color: bool = True
    verbose: bool = False
    timeout_seconds: int = 30
    max_retries: int = 3
    confirm_destructive: bool = True

    @classmethod
    def load(cls) -> "Config":
        """Load config from environment variables."""
        config = cls()
        
        if fmt := os.environ.get("MONARCH_FORMAT"):
            try:
                config.format = OutputFormat(fmt.lower())
            except ValueError:
                pass
        
        if os.environ.get("NO_COLOR") or os.environ.get("MONARCH_NO_COLOR") == "1":
            config.color = False
        
        if os.environ.get("MONARCH_VERBOSE") == "1":
            config.verbose = True
        
        # Parse timeout and retries...
        return config

_config: Config | None = None

def get_config() -> Config:
    """Get the global config instance."""
    global _config
    if _config is None:
        _config = Config.load()
    return _config
```

## Config Precedence
1. CLI flags (--format json) - highest
2. Environment variables (MONARCH_FORMAT=json)
3. Config defaults - lowest

## NO_COLOR Standard
Respect the NO_COLOR environment variable (https://no-color.org/):
- If NO_COLOR is set (to any value), disable colors
- MONARCH_NO_COLOR=1 is CLI-specific alternative

## Deferred to v1.1
- TOML config file (~/.config/monarch-cli/config.toml)
- `monarch config` commands (show, set, path)

## Acceptance Criteria

- [ ] Config dataclass with all settings
- [ ] get_config() returns singleton instance
- [ ] MONARCH_FORMAT env var works
- [ ] MONARCH_TIMEOUT env var works
- [ ] MONARCH_VERBOSE env var works
- [ ] NO_COLOR disables colors
- [ ] get_config_dir() uses platformdirs
- [ ] MONARCH_CONFIG_DIR override works
- [ ] Unit tests for config loading

