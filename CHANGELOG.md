# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

#### Layered Configuration System
- **Config file support** - Create `~/.config/monarch-cli/config.toml` for persistent settings
- **Layered precedence** - Config file → Environment variables → CLI flags (highest priority)
- **Source tracking** - `config.get_source("key")` returns where each setting came from (`default`, `file`, `env`, or `cli`)
- **`--timeout` flag** - Override API request timeout per-command (e.g., `monarch accounts list --timeout 60`)

#### Network Resilience
- **Automatic retry** - API calls now retry on transient network errors with exponential backoff
- **Configurable timeout** - `MONARCH_TIMEOUT` and config file `timeout` setting now functional
- **Configurable retries** - `MONARCH_MAX_RETRIES` and config file `max_retries` setting now functional

#### Transaction Attachments
- **Receipt upload command** - `monarch transactions attach TXN123 ./receipt.pdf` uploads a receipt or supporting document to a transaction.
- **Atomic receipt workflow** - `--notes` can update transaction notes after a successful attachment upload.
- **Upload preview** - `--dry-run` validates the file and reports the planned attachment without authenticating or mutating Monarch.

#### API Coverage
- **Account workflows** - Added account history, holdings, recent balances, snapshots, manual account create/update/delete, balance-history upload, refresh waiting, and refresh status commands.
- **Transaction workflows** - Added create/show/delete/duplicates, full list filters, report/review/goal update flags, tag list/create/set/remove/clear, and split show/update commands.
- **Budget workflows** - Added explicit date ranges, reset, category/group budget updates, flexible budget updates, and flex rollover settings.
- **Category workflows** - Added category groups, create, and guarded single/bulk delete commands.
- **Reports workflows** - Added detailed cashflow, transactions summary, recurring transactions, credit history, subscription details, and linked institutions commands.
- **Idempotent manual transactions** - `transactions create` now supports repeatable `--tag` and optional `--dedupe-key`; `transactions upsert` creates only when the default dedupe key does not match an existing row.

#### Agent Ergonomics
- **Capabilities manifest** - Added `monarch capabilities --json` with deterministic command, flag, argument, exit code, environment variable, and config/session file metadata.
- **Non-interactive mode** - Added global `--non-interactive`, `MONARCH_NON_INTERACTIVE`, and `CI` prompt guards. Commands that would prompt now fail fast with exit code `4`.
- **Exit-code contract** - Documented `0` success, `1` general error, `2` usage error, and `4` input needed in help, docs, and the capabilities manifest.
- **JSON auth errors** - Auth commands with explicit `--json` now emit structured JSON errors on stdout instead of leaving stdout empty.

### Changed

- **Default output format** - Changed from `json` to `plain` for interactive terminal use
  - TTY: Human-friendly output with emoji icons
  - Piped/redirected: Automatic JSON output (backwards compatible)
- **Transaction create output** - `transactions create --json` now normalizes the upstream `createTransaction.transaction.id` response to a top-level `id` and includes normalized readback fields for safer scripts.
- **Mutation output schemas** - Account, budget, category, and transaction write commands now accept subcommand-local `--json`/`--format` flags and return normalized envelopes with `status`, `entity`, top-level `id`/`ids`, and `result`.

### Fixed

- **Color auto-detection** - `NO_COLOR`, `TERM=dumb`, and non-TTY now properly disable color
  - Previously, color settings bypassed auto-detection, causing ANSI codes in piped output
- **Environment variables** - `MONARCH_TIMEOUT`, `MONARCH_MAX_RETRIES` were documented but non-functional; now wired up to actual API calls
- **Manual transaction merchant readback** - Created manual transactions preserve the requested merchant name in normalized output when Monarch returns a blank `plaidName`.
- **State-file diagnostics** - Corrupt config/session JSON or TOML files are copied to `*.corrupt.<timestamp>` with a warning instead of being silently ignored.

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
- `MONARCH_TOKEN` - Direct token authentication (for CI/automation)
- `MONARCH_FORMAT` - Default output format preference
- `MONARCH_TIMEOUT` - Request timeout in seconds
- `MONARCH_VERBOSE` - Enable verbose output
- `NO_COLOR` / `MONARCH_NO_COLOR` - Disable colored output

### Security

- Session tokens stored securely in `~/.config/monarch/session.json`
- No credentials stored after authentication
- Token refresh handled automatically

[Unreleased]: https://github.com/crcatala/monarch-cli/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/crcatala/monarch-cli/releases/tag/v0.1.0
