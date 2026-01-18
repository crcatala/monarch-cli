# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Additional output formats (planned)

### Changed

- Nothing yet

## [0.1.0] - 2026-01-18

Initial release of Monarch CLI - a command-line interface for Monarch Money.

### Added

#### Authentication Commands
- `monarch auth login` - Interactive login with email/password and optional MFA support
- `monarch auth status` - Show current authentication status
- `monarch auth logout` - Log out and clear stored credentials
- `monarch auth doctor` - Diagnose authentication setup issues
- `monarch auth ping` - Test API connectivity
- `monarch auth setup` - Show setup instructions for new users

#### Account Commands
- `monarch accounts list` - List all linked financial accounts with balances
- `monarch accounts refresh` - Request account refresh from linked institutions

#### Transaction Commands
- `monarch transactions list` - List transactions with powerful filtering options
  - Filter by date range, account, category, amount, search text
  - Support for date presets (today, yesterday, this-week, this-month, etc.)
- `monarch transactions update` - Update transaction properties (notes, category, tags)
- `monarch transactions batch-update` - Batch update multiple transactions at once

#### Budget Commands
- `monarch budgets list` - List all budgets with progress and remaining amounts

#### Cashflow Commands
- `monarch cashflow summary` - View income/expense summary for a date range

#### Category Commands
- `monarch categories list` - List all transaction categories

#### Output Formats
- Multiple output formats: plain, json, table, csv, ndjson, compact
- Auto-detection: JSON when piped, human-friendly in terminal
- `--json` flag to force JSON output
- `--quiet` flag for minimal output (IDs only)
- `--no-color` flag to disable colored output

#### AI Agent Integration
- Stable JSON schema designed for AI agent consumption
- Auto-JSON detection when stdout is piped
- Documented schema contracts for accounts and transactions
- Exit codes and error handling optimized for programmatic use

#### Developer Experience
- Shell completion support for bash, zsh, and fish
- `--verbose` flag for operational progress messages
- `--debug` flag for stack traces on errors
- Comprehensive test suite (91% coverage)
- Type hints throughout codebase

#### Configuration
- `MONARCH_CONFIG_DIR` - Custom config directory location
- `MONARCH_SESSION_TOKEN` - Direct token authentication
- `MONARCH_OUTPUT_FORMAT` - Default output format preference

### Security

- Session tokens stored securely in `~/.config/monarch/session.json`
- No credentials stored after authentication
- Token refresh handled automatically

[Unreleased]: https://github.com/yourusername/monarch-cli/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/yourusername/monarch-cli/releases/tag/v0.1.0
