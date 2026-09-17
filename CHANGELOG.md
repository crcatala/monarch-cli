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

#### Mutation Retry Safety
- **Remote mutations never retry automatically** - Account refresh, transaction update, and each batch-update item execute exactly once; the configured retry behavior now applies to read commands only (a timed-out write may already have been applied)
- **Ambiguity is distinct from failure** - When a mutation request may have been dispatched but its outcome is unknown (timeout, disconnect, cancellation after invocation, or Ctrl-C), the CLI emits the structured `MUTATION_AMBIGUOUS` error with exit code `4`, identifying the operation and affected record ID(s) with a safe verification step instead of claiming the operation failed
- **Batch update per-item outcomes** - `transactions batch-update` reports an ordered `mutation-outcome.v1` item for every input ID and exits nonzero when any item is failed or ambiguous
- **No generic retry override** - Any future mutation retry must select a named, operation-specific mechanism (`idempotency_key` or `read_after_write`) with operation-specific tests before the executor accepts it

#### Mutation Outcome Contract (`mutation-outcome.v1`)
- **One shared envelope for every remote mutation** - Account refresh, transaction update, and each batch-update item return the versioned `mutation-outcome.v1` envelope (`schema_version`, `operation`, `status`, `summary`, `items`, `verification`) on stdout after the request is attempted; see `docs/mutation-outcomes.md`
- **Deterministic top-level statuses** - `succeeded` (exit 0), `failed` (normal nonzero error exit), `ambiguous` (exit 4), and `partial` for mixed item outcomes (exit 4); batch items preserve input order and multi-stage workflows preserve remote-effect order
- **Required verification for ambiguity** - Any ambiguous item forces a `verification` object with `required: true`, an actionable message, and a tokenized safe command when one exists
- **Sanitized structured errors** - Item error objects carry stable `code`, `message`, and object-valued `details`; raw exception text, request bodies, and credentials never reach the contract
- **Breaking changes need a new version** - Envelope fields, status values, and exit-code semantics are additive only; removals or semantic changes require `mutation-outcome.v2` or later

### Changed

- **Default output format** - Changed from `json` to `plain` for interactive terminal use
  - TTY: Human-friendly output with emoji icons
  - Piped/redirected: Automatic JSON output (backwards compatible)

### Removed

#### Legacy Pickle Session Support (breaking)
- **Pickle session format is no longer read, written, or migrated** - Pickle deserialization can execute arbitrary code, so the legacy `~/.mm/mm_session.pickle` file is never deserialized
- **`StorageBackend.FILE_COMPAT` (`file-compat`) removed** - The `file-compat` storage option is gone from `auth login` and `auth logout`; supported backends are `keyring`, `file`, and `MONARCH_TOKEN`
- **Forced re-authentication** - Users with only a legacy pickle session must run `monarch auth login` again; there is no migration path
- **Presence-only detection** - `auth status`, `auth doctor`, and authentication failures report that a legacy artifact exists (filesystem metadata only) and direct users to `monarch auth login`; the file is never read and never deleted by the CLI (remove it yourself with `rm ~/.mm/mm_session.pickle`)

### Fixed

- **Color auto-detection** - `NO_COLOR`, `TERM=dumb`, and non-TTY now properly disable color
  - Previously, color settings bypassed auto-detection, causing ANSI codes in piped output
- **Environment variables** - `MONARCH_TIMEOUT`, `MONARCH_MAX_RETRIES` were documented but non-functional; now wired up to actual API calls

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
