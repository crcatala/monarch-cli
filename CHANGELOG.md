# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

#### Dry-run previews for tag and split mutations
- `transactions tags replace`/`add`/`clear` and `transactions splits replace`/`clear` accept `--dry-run` (mc-7lm1)
- A preview performs only read/validation work: it never calls a mutation endpoint, never requires `--allow-mutations`, and never prompts; `--dry-run --yes` is accepted as irrelevant
- Preview results carry `status: "dry_run"` with the operation, target, and an informational detail object; they use the shared JSON emission path and are distinct from `mutation-outcome.v1`

#### Validation and flag interaction semantics
- `--timeout` must be >= 1; `transactions batch-update --max-concurrency` must be 1-16 (rejects 0/negative/out-of-range before any API call) — mc-s6s6
- Date options use one strict `YYYY-MM-DD` parser; compact/loose forms (`20240115`, `2024-1-5`) fail with `INVALID_INPUT`
- Transaction update amounts reject NaN/infinity; `--raw` rejects normalized-only options (`institutions list --include-deleted`, `investments holdings --aggregate`); `--quiet` errors when a returned record has no extractable ID
- Keyring guidance recommends `--storage=file`; `--yes` is documented as confirmation bypass only and never authorizes a write

#### Transaction tag assignment redesign and additive `add`
- `transactions tags replace`/`clear` require `--transaction-id` and use repeatable `--tag-id`/`--tag-name` options instead of positional arguments; `transactions tags add` is new (mc-46gq)
- Tag names resolve through household discovery with exact, case-sensitive matching; unknown names/IDs and duplicate-name ambiguities are pre-mutation errors
- `add` is a read-modify-write over the full-set endpoint, preserves existing (including stale) tags, deduplicates, and reports `added`/`skipped`/`no_op`; it is not atomic against concurrent changes
- The README no longer states that incremental tag additions are never exposed

#### Explicit transaction mutation targets
- `transactions update`, `transactions batch-update`, `transactions splits replace`, and `transactions splits clear` now require `--transaction-id` and no longer accept positional transaction IDs; a removed positional produces an actionable usage error pointing at `--transaction-id` (mc-vv11)
- `transactions batch-update` accepts repeatable `--transaction-id` options (repeatable values first, then `--stdin`), deduplicated in first-seen order
- The legacy split source aliases `--json-input`, `--input-json`, `--file`, and `--input-file` are removed; use `--splits-json` or `--splits-file`

#### Consistent global options and machine-readable mutation output
- Root global options must precede the command path (`monarch [GLOBAL OPTIONS] GROUP COMMAND [COMMAND OPTIONS]`); README/help examples that placed `--timeout`, `--no-color`, `--verbose`, or `--quiet` after the command path are corrected (mc-hu2c)
- `auth status` and `auth ping` now resolve output through the shared effective format, so `monarch --json auth status` matches `monarch auth status --json` and a piped `monarch auth status` emits JSON
- Remote mutation outcomes and dry-run previews always emit JSON on stdout regardless of TTY state; `--quiet` and an explicit non-JSON format are rejected with `INVALID_INPUT` (exit 2) before any mutation is attempted
- **Default output format** - Changed from `json` to `plain` for interactive terminal use; TTY output is human-friendly while piped/redirected output remains automatic JSON
- **Concise-format contract** - `compact` uses the same curated field subset as `plain`/`table`; `json`, `csv`, and `ndjson` retain complete normalized records

### Added

#### Transaction discovery and detail
- Expanded `transactions list` with repeatable account/category/tag filters, tri-state status filters, visibility controls, and bounded pagination
- Added read-only `transactions get TXN_ID` with normalized detail; pending IDs redirect by default, while `--strict` disables that redirect

#### Transaction tag workflows
- Added read-only tag discovery and assignment inspection through `transactions tags list` and `transactions tags show`
- Added validated `transactions tags create` plus guarded complete-set replacement and clearing; IDs and names are checked before a write and remote results use the shared mutation outcome contract

#### Transaction split workflows
- Added read-only `transactions splits show` and guarded complete-set `replace`/`clear` operations
- Split JSON is bounded and validated against the parent transaction total; writes are read back for verification and ambiguous results include safe inspection guidance

#### Account history and refresh visibility
- Added `accounts history`, `recent-balances`, `snapshots`, and `snapshots-by-type` for normalized balance and net-worth history
- Added read-only `accounts refresh-status`, including explicit unknown-account results rather than treating them as complete

#### Cashflow and transaction reporting
- Added `cashflow detail` with normalized category, category-group, merchant, and summary aggregates
- Added `transactions summary` for all-time aggregates and `transactions recurring` for date-scoped recurring activity

#### Investment holdings
- Added read-only `investments holdings` with account selection, hidden-account opt-in, bounded concurrent retrieval, and optional security-ID aggregation; missing financial values remain `null`

#### CLI help polish
- Every remote-mutation command's help documents that the global `--allow-mutations` option is required and must be placed before the command path, and documents `--dry-run` where supported (mc-4z49)
- Root/group/representative-command help reviewed for concise descriptions and examples; a help-contract test driven by the mutation inventory enforces the guidance for current and future mutations

#### Liability and Debt-Service Account Metadata
- **Direct asset/liability classification** - `is_asset` mirrors the upstream `isAsset` flag; unavailable classifications stay `null` and liability is never inferred from display labels
- **Liability metadata in `monarch accounts list`** - Distinct nullable `credit_limit`, `provider_credit_limit`, `apr`, `interest_rate`, `minimum_payment`, `planned_payment`, and `excluded_from_debt_paydown` fields; provider and user-facing values never merge; missing values stay `null`, never fabricated zeroes
- **Stable type/subtype identifiers** - `type_name` and `subtype_name` mirror the upstream `name` identifiers used by `monarch accounts types`; `type`/`subtype` remain display labels
- **Literal passthrough** - Rate values keep upstream numeric units (no scaling); upstream does not document snapshot-vs-setting semantics for planned/provider/minimum values, and no claim is made

#### Household Ownership Visibility
- **`owner_id` / `owner_name` in account output** - Normalized account records mirror the optional upstream `ownedByUser` relationship (`id` and `displayName`), so shared-household activity can be separated by person
- **`owner_id` / `owner_name` / `ownership_overridden_at` in transaction output** - List and detail records expose the upstream ownership relationship (`id` and `name`) and pass the override timestamp through literally; no actor, previous owner, or boolean shared state is ever derived
- **Null ownership stays null** - A missing, null, or malformed owner relationship yields null owner fields; null ownership does not distinguish shared, unassigned, unavailable, or unsupported upstream states because the released upstream response cannot
- **Read-only attribution** - No command mutates ownership or any remote state; `--raw` remains byte-for-structure untouched and quiet mode remains ID-only

#### Institution and Subscription Status
- **`monarch institutions list`** - Credential-centric connection diagnostics with provider/institution status and associated accounts
- **Deleted-account safety** - Deleted accounts are excluded by default; `--include-deleted` opts in while retaining `is_deleted` and `deleted_at`
- **`monarch subscription show`** - One normalized contract for trial and premium-entitlement state, with unavailable data distinct from known false values
- **Privacy-minimized defaults** - Referral and payment-source metadata are excluded from normalized output; explicit `--raw` preserves the upstream response
- **Read-only operations** - Both commands use the released `monarchmoneycommunity>=1.5.2` client methods and never initiate remote mutations

#### Account Type Discovery
- **`monarch accounts types`** - Read-only discovery of the supported account groups, types, and subtypes accepted by account workflows, so callers no longer have to guess identifiers
- **Normalized hierarchy records** - One stable record per `(group, type, subtype)` leaf with `group`, `type`, `type_display`, `subtype`, and `subtype_display` fields; identifiers are the upstream `name` values and labels are human-readable `display` values
- **Deterministic ordering** - Types follow upstream first-seen order; within a type, subtypes follow the upstream `possibleSubtypes` order; duplicate identifiers collapse (first wins)
- **Null-safe evolution** - Empty, null, partial, and unknown option fields normalize without crashes or invented values; `--raw` returns the upstream payload untouched

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
- **Normalization at upstream API boundaries** - Account, transaction, and cashflow transformers now tolerate present-but-null or missing nested relationships, summary blocks, and collection containers instead of raising `AttributeError`/`TypeError`; a non-object top-level payload fails deliberately with a typed `APIError`; raw passthrough is unchanged
- **Released read-shape compatibility** - Snapshot requests serialize validated dates as ISO strings, while transaction summary and cashflow detail normalize the list/object envelopes returned by the released client without dropping aggregate values
- **Transaction pending state** - `is_pending` now reads the real upstream `pending` field instead of the incorrect `isPending` key (which made it always `false`)

### Security

#### Credential-safe third-party upload transport
- Added `monarch_cli.core.upload_transport`, a public adapter boundary for the transaction-attachment upload path that builds third-party media requests from explicit destination and signed-field allowlists instead of copying and pruning the authenticated client's headers
- The transport pins the media destination, refuses redirects so credential headers can never cross origins, and keeps signed-parameter acquisition, media upload, and attachment registration as distinct stages; signed material and raw responses never reach logs, structured errors, or diagnostics
- Commands and services never call `MonarchMoney.upload_attachment()` or its private upload methods directly; the released client is unpatched and `monarchmoneycommunity` 1.5.2 is the current floor, so the local adapter and its maintenance assumptions are documented in [docs/upload-transport.md](docs/upload-transport.md)

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
