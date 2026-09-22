# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.1] - 2026-09-21

### Added

#### Normalized institution status
- `institutions list` now exposes the upstream overall institution status as
  `institution_status`, alongside the existing credential-connection, issue,
  balance, and transaction status fields (mc-oqc9).

## [0.2.0] - 2026-09-19

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

#### Deterministic CLI capabilities manifest (mc-82kf)
- Added side-effect-free `monarch capabilities`, which prints one versioned JSON manifest (`capabilities.v1`) describing every command path, argument, option, required input, default, output support, safety requirement, interactivity, and published contract version
- Command effects, safety policy, interactivity, preview support, and output support are declared as explicit shared metadata; framework introspection discovers syntax only and never determines safety or output behavior
- Stable schema identifiers and contract versions are consumed from the `mc-cpzi` mapping rather than duplicated; raw passthrough is marked explicitly unstable and unschematized
- Generation performs no authentication lookup, client construction, network request, prompt, or config/session creation or write
- A canonical fixture test pins manifest shape, ordering, and byte-for-byte serialization; completeness tests fail when a registered command is missing metadata, metadata disagrees with the shared execution policy, a schema reference is unknown, or the inventory is empty or partial
- Documented discovery, versioning, stability, and raw-output caveats in `docs/capabilities.md`

#### Published machine-readable output schemas (mc-cpzi)
- Published checked-in JSON Schema Draft 2020-12 artifacts for normalized account, transaction (list), transaction detail, structured error, and `mutation-outcome.v1`; each carries a stable versioned URN `$id` (for example `urn:monarch-cli:schema:account:v1`) and ships as a package resource in the wheel and sdist
- Added the `monarch_cli.schemas` module-level mapping resolving contract name/version and URN to the packaged artifact, plus the shared operation/effect-entity mapping (`transactions.attachments.add` uses `attachment_media` and `attachment`)
- Published schemas use `additionalProperties: false` so undocumented stable fields and removals fail validation; mutation-outcome fixtures cover successful, definitive-stage-failure, ambiguous-registration, and partial/orphaned-media attachment outcomes
- Documented the compatibility policy (optional additions and open error-code additions are additive; removals, required-field additions, type/nullability changes, and closed-enum changes require a new version) and how to locate, resolve, validate, and migrate schemas in `docs/schema-contracts.md`
- JSON Schema validation remains development/test-only (`jsonschema` is a dev extra); schemas are resolved from package resources and the CLI adds no runtime schema dependency

#### Transaction discovery and detail
- Expanded `transactions list` with repeatable account/category/tag filters, tri-state status filters, visibility controls, and bounded pagination
- Added read-only `transactions get TXN_ID` with normalized detail; pending IDs redirect by default, while `--strict` disables that redirect
- Normalized transaction detail now exposes review attribution `reviewed_at` (literal upstream `reviewedAt`) and `reviewed_by_user` (normalized `reviewedByUser` `{id, name}`, or `null`), matching the review commands' output shape (mc-61tf); both are optional additive properties on `transaction-detail:v1` (no version bump) and detail-only
- Documented that the opaque `review_status` field is not selected by the released detail read and is therefore always `null` in normalized detail (a placeholder); `reviewed_at`/`reviewed_by_user` carry review attribution, while the list read is the surface that requests `reviewStatus`

#### Transaction tag workflows
- Added read-only tag discovery and assignment inspection through `transactions tags list` and `transactions tags show`
- Added validated `transactions tags create` plus guarded complete-set replacement and clearing; IDs and names are checked before a write and remote results use the shared mutation outcome contract

#### Transaction split workflows
- Added read-only `transactions splits show` and guarded complete-set `replace`/`clear` operations
- Split JSON is bounded and validated against the parent transaction total; writes are read back for verification and ambiguous results include safe inspection guidance

#### Transaction attachment upload
- Added `transactions attachments add` (mc-2v9a): attach one supported local file to an explicitly identified transaction via a three-stage workflow (signed-parameter acquisition, credential-safe media upload, registration)
- Requires `--transaction-id` and `--file` (with an optional validated `--filename` override) and never accepts positional arguments; local file policy is documented (`.pdf`/`.jpg`/`.jpeg`/`.png`/`.gif`/`.webp`, 10 MiB cap, single `O_NOFOLLOW` descriptor, symlink/directory/empty/content-mismatch rejection)
- `--dry-run` is fully offline and reports only target ID, sanitized basename, size, and inferred type; the local path and file contents never appear in output or diagnostics
- The workflow consumes only the reviewed `mc-sr92` upload adapter, makes one attempt per media/registration stage, verifies registration by returned identity through transaction detail, and reports orphaned-asset partial completion honestly with no rollback claim

#### Guarded monthly category budget updates
- Added `budgets set --category-id CATEGORY_ID --amount AMOUNT --start YYYY-MM-DD` (mc-9u99): sets the monthly amount for exactly one category in one explicitly identified month; `--start` must be the first day of a month
- All local validation (identifier, strict date, finite/non-negative amount, cent precision) precedes authentication, authorization, and every API call; the exact category is validated against bounded read-only discovery before the write
- The write uses the released `set_budget_amount` capability with exactly the category target, amount, `timeframe="month"`, the requested start date, and `apply_to_future=False`; no category-group target or future-month flag is sent
- After the write, the exact category/month planned amount is read back and compared using exact cent-normalized equality; a rejection, transport ambiguity, malformed response, unavailable readback, or mismatch is never reported as success and is never blindly retried
- Emits `mutation-outcome.v1` with stable operation `budgets.set` and entity `budget`; `--dry-run` validates and previews without writing; a zero amount is a deliberate reset-to-zero
- Out of scope and not exposed: future-month propagation, category groups, flexible budgets, whole-budget reset, rollover settings, and bulk updates

#### Explicit transaction review-state mutations
- Added intent-oriented `transactions review mark` (`reviewed=True`, omits `needsReview`) and `transactions review return` (`needsReview=True`, omits `reviewed`); both require `--transaction-id` and never accept positional arguments (mc-e49c)
- `reviewed=False`, `needsReview=False`, and contradictory review-state combinations are not accepted by this surface
- The serialized mutation input contains only the transaction ID and the one intended review-state field; a narrow local GraphQL adapter (resolution option 3, documented maintenance ownership) avoids the released upstream helper's unrelated `category: null` / `name: null` inputs
- A pre-read (no pending redirect) verifies exact identity and returns a deterministic no-op when the requested state is already observed; a post-read confirms the intended review state and that category and merchant identity were unchanged
- Successful output reports observed `needs_review`, `reviewed_at`, and `reviewed_by_user` and never invents a `reviewed` boolean; uncertain writes use the retry-safe mutation executor and report ambiguity (exit 4) with a tokenized `monarch transactions get TXN_ID` verification command

#### Manual transaction create and delete
- Added `transactions create` and `transactions delete` (mc-yqfi): a minimal single-transaction lifecycle built on the shared mutation policy, retry-safe executor, and `mutation-outcome.v1` contract
- `transactions create` requires `--date`, `--account-id`, `--amount`, `--merchant`, and `--category-id` (optional `--notes`); `transactions delete` requires `--transaction-id`; neither accepts positional targets
- Local validation (empty IDs/merchant, invalid date, non-finite amount, malformed combinations) completes before authentication, authorization, or any API call; both commands are classified `remote_mutation` and require global `--allow-mutations`
- `--dry-run` for both commands is local-only: no authentication, client, or network call, and it reports the planned target/input without claiming a remote effect
- Create uses the released public `create_transaction` capability, makes one attempt, extracts the returned ID, and performs a bounded non-redirecting exact-ID readback that verifies date, amount, account, category, merchant, and notes where exposed; a missing/malformed ID, timeout, disconnect, or mismatch is ambiguous (exit 4) with verification guidance and is never retried
- Delete is single-target only, requires destructive confirmation (`--yes` bypasses the prompt but never authorizes), reads the exact target first, makes one attempt, and verifies absence; a lost or contradictory result is ambiguous rather than a claimed deletion
- Neither command claims idempotency or recoverability, and the first version deliberately excludes tags, dedupe/upsert, duplicate detection, batch operations, `--update-balance`, attachments, and account/category management

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
- **gql transport failures during mutations** - A dispatched mutation whose transport fails is now reported `ambiguous` (exit 4, `remote_state: unknown`, verification hint) instead of a definitive `failed` with `code: UNKNOWN` (mc-ic7w). The upstream client performs every call through the gql transport, which wraps all connection-level failures as `gql.transport.exceptions.TransportConnectionFailed`; that type is now classified as an ambiguous/retryable transport failure, as are the other connection-level gql transport failures (protocol errors and 5xx server errors), while GraphQL `errors` payloads and 4xx server responses remain definitive failures. Mutations still make exactly one attempt.

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

[Unreleased]: https://github.com/crcatala/monarch-cli/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/crcatala/monarch-cli/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/crcatala/monarch-cli/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/crcatala/monarch-cli/releases/tag/v0.1.0
