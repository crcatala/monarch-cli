# Command reference

This is the concise reference for the current CLI surface. Run
`monarch COMMAND --help` for the exact generated help for an installed build.

Placeholders used below:

- `ACC_ID` — account ID
- `TXN_ID` — transaction ID
- `CAT_ID` — category ID
- `TAG_ID` — transaction-tag ID

## Capabilities discovery

`monarch capabilities` prints a versioned, machine-readable JSON manifest of
the installed CLI: every command path, argument, option, required input,
default, output support, safety requirement, interactivity, and published
contract version. It is side-effect free (no authentication, network, prompt,
or config/session write). See [Capabilities manifest](capabilities.md).

```bash
monarch capabilities | jq '.commands[] | select(.safety.requires_authorization)'
```

## Global options

Global options appear before the command path:

```text
monarch [GLOBAL OPTIONS] GROUP COMMAND [COMMAND OPTIONS]
```

| Option | Purpose |
|---|---|
| `-v, --version` | Show the version and exit |
| `-V, --verbose` | Show operational progress |
| `--debug` | Show stack traces; implies verbose |
| `--json` | Set JSON as the output default |
| `-q, --quiet` | Emit only IDs, one per line |
| `--no-color` | Disable colored output |
| `--timeout SECONDS` | API timeout; must be at least `1` |
| `--allow-mutations` | Authorize remote writes for this invocation |
| `--yes` | Skip destructive confirmation; does not authorize writes |
| `--non-interactive` | Fail instead of prompting |
| `--install-completion SHELL` | Install shell completion |
| `--show-completion SHELL` | Print shell completion |
| `--help` | Show help |

`--allow-mutations` is never persisted and has no environment-variable
equivalent. `--yes` only affects commands that request destructive
confirmation. `--non-interactive` also accepts `MONARCH_NON_INTERACTIVE=1` or
the `non_interactive = true` configuration setting.

## Shared output options

Most read commands accept:

```text
-f, --format plain|json|table|csv|compact
--json
```

The default is human-readable plain output on a TTY and JSON when stdout is
piped or redirected. `compact` is single-line JSON. `--raw` is available only
where noted and bypasses normalization. `--ndjson` is available on
`accounts list` and `transactions list`.

Mutation results and dry-run previews always emit JSON. They reject
`--quiet` and explicit non-JSON formats before any remote write.

## Date presets

Commands that accept `--preset` support:

```text
today, yesterday, this-week, last-week,
this-month, last-month, last-30-days, last-90-days,
this-year, last-year, ytd, all
```

Explicit dates use strict `YYYY-MM-DD` values. Commands that require an
explicit range require both `--start` and `--end`.

## Authentication

### `auth login`

Interactively logs in, handles MFA, and stores the resulting token.

Options:

- `-s, --storage keyring|file`

```bash
monarch auth login
monarch auth login --storage keyring
monarch auth login --storage file
```

### `auth status`

Shows whether credentials are available and which backend is active.

Options:

- `--json`

```bash
monarch auth status --json
```

### `auth logout`

Clears credentials from all backends, or one selected backend.

Options:

- `-s, --storage keyring|file`

```bash
monarch auth logout
monarch auth logout --storage file
```

### `auth doctor`

Reports keyring availability, token locations, legacy artifacts, and API
connectivity when authenticated.

```bash
monarch auth doctor
```

### `auth ping`

Makes a simple authenticated API request.

Options:

- `--json`

```bash
monarch auth ping --json
```

### `auth setup`

Prints authentication, storage, security, and troubleshooting instructions.

```bash
monarch auth setup
```

## Accounts

### `accounts list`

Lists all linked accounts with normalized balances and metadata.

Options:

- Shared output options
- `--ndjson`
- `--raw`

```bash
monarch accounts list --format table
monarch accounts list --raw --json
monarch --quiet accounts list
```

### `accounts types`

Lists authoritative account group, type, and subtype identifiers.

Options:

- Shared output options
- `--raw`

```bash
monarch accounts types --json
```

### `accounts history ACC_ID`

Shows normalized balance history for one account. The ID is opaque and is sent
to the API unchanged.

Options:

- Shared output options
- `--raw`

```bash
monarch accounts history ACC_ID --json
```

### `accounts recent-balances`

Shows recent daily balances for all accounts. Without `--start`, the upstream
default is used, currently the last 31 days.

Options:

- `-s, --start YYYY-MM-DD`
- Shared output options
- `--raw`

```bash
monarch accounts recent-balances --start 2024-01-01 --json
```

### `accounts snapshots`

Shows aggregate net-worth snapshots over a date range.

Options:

- Required `-s, --start YYYY-MM-DD`
- Required `-e, --end YYYY-MM-DD`
- `-t, --account-type TYPE`
- Shared output options
- `--raw`

The optional type identifier is validated against `accounts types`.

```bash
monarch accounts snapshots \
  --start 2024-01-01 \
  --end 2024-12-31 \
  --account-type depository \
  --json
```

### `accounts snapshots-by-type`

Shows type-scoped snapshots at monthly or yearly granularity.

Options:

- Required `-s, --start YYYY-MM-DD`
- Required `--timeframe month|year`
- Shared output options
- `--raw`

```bash
monarch accounts snapshots-by-type \
  --start 2020-01-01 \
  --timeframe year \
  --json
```

### `accounts refresh-status`

Observes synchronization state. It does not initiate, poll, or wait for a
refresh.

Options:

- `-a, --account ACC_ID` — repeatable; checks all accounts when omitted
- Shared output options

```bash
monarch accounts refresh-status --account ACC_ID --json
```

### `accounts refresh`

Requests a background refresh from linked institutions. This is a remote
mutation.

Options:

- `-a, --account ACC_ID` — repeatable; refreshes all accounts when omitted

```bash
monarch --allow-mutations accounts refresh
monarch --allow-mutations accounts refresh -a ACC_ID
```

## Budgets

### `budgets list`

Lists current budget categories with budgeted, spent, and remaining amounts.
Spent values are normalized as positive numbers.

Options:

- Shared output options

```bash
monarch budgets list --format table
monarch budgets list --json
```

### `budgets set`

Sets the monthly amount for exactly one category in one explicitly identified
month. `--start` is required and must be the first day of a month
(`YYYY-MM-01`). `--amount` must be a finite, non-negative value with at most two
decimal places; a zero amount deliberately resets the category's monthly budget
to zero. The command validates the exact category against read-only category
discovery before the write and reads the exact category/month amount back
afterward.

This scope never propagates to future months, targets a category group, updates
flexible budgets, resets an entire budget, or changes rollover settings. It
therefore exposes no `--group`, `--future`, flexible-budget, reset, or rollover
options.

Options:

- `--category-id CATEGORY_ID` — required; exact category target
- `--amount AMOUNT` — required; finite, non-negative, max 2 decimals
- `--start YYYY-MM-01` — required; monthly period start (first of month)
- `--dry-run` — validate and preview without writing

This is a remote mutation and requires the global `--allow-mutations` option
**before** the command path. It uses the shared single-attempt mutation executor
and emits `mutation-outcome.v1` with operation `budgets.set` and entity `budget`;
an unknown category, transport ambiguity, or a readback mismatch is never
reported as success and is never retried blindly. The readback comparison is
exact equality after normalizing both amounts to whole cents.

```bash
monarch --allow-mutations budgets set --category-id CAT123 --amount 500.00 --start 2026-09-01
monarch budgets set --category-id CAT123 --amount 500.00 --start 2026-09-01 --dry-run
```

## Cashflow

### `cashflow summary`

Reports income, expenses, savings, and savings rate for a period.

Options:

- `-s, --start YYYY-MM-DD`
- `-e, --end YYYY-MM-DD`
- `-p, --preset PRESET`
- Shared output options

```bash
monarch cashflow summary --preset this-month --json
monarch cashflow summary --preset ytd --format table
```

### `cashflow detail`

Returns category, category-group, merchant, and overall cashflow detail in one
aggregate request.

Options:

- Same date and preset options as `cashflow summary`
- Shared output options
- `--raw`

```bash
monarch cashflow detail --preset last-90-days --json
monarch cashflow detail \
  --start 2024-01-01 \
  --end 2024-03-31 \
  --raw
```

## Categories

### `categories list`

Lists transaction categories with IDs, names, groups, and icons.

Options:

- Shared output options

```bash
monarch categories list --json
monarch categories list --format csv > categories.csv
```

## Institutions and subscriptions

### `institutions list`

Lists credential-centric institution connection status and associated accounts.
Deleted accounts are excluded by default.

Options:

- `--include-deleted`
- Shared output options
- `--raw`

`--include-deleted` is incompatible with `--raw` because it only shapes
normalized output.

```bash
monarch institutions list --include-deleted --json
monarch institutions list --raw --json
```

### `subscription show`

Shows normalized trial and premium-entitlement state.

Options:

- Shared output options
- `--raw`

```bash
monarch subscription show --json
monarch subscription show --raw --json
```

## Investments

### `investments holdings`

Lists holdings across eligible investment accounts.

Options:

- `-a, --account ACC_ID` — repeatable
- `--include-hidden`
- `--aggregate`
- `--raw`
- Shared output options

Automatic discovery excludes hidden accounts and accounts reporting zero
holdings. Explicit account IDs are validated against account discovery.
`--aggregate` and `--raw` are incompatible.

```bash
monarch investments holdings --json
monarch investments holdings --include-hidden --format table
monarch investments holdings --account ACC1 --account ACC2 --json
monarch investments holdings --aggregate --json
monarch investments holdings --raw --json
```

See [Investment holdings](investment-holdings.md) for selection,
aggregation, currency, and raw-output behavior.

## Transactions

### `transactions list`

Lists transactions with pagination, date, identity, state, origin, visibility,
and text filters.

Options:

- `-l, --limit INT` — default `100`, maximum `1000`
- `-o, --offset INT` — default `0`
- `-s, --start YYYY-MM-DD`
- `-e, --end YYYY-MM-DD`
- `-p, --preset PRESET`
- `-a, --account ACC_ID` — repeatable
- `-c, --category CAT_ID` — repeatable
- `-t, --tag TAG_ID` — repeatable
- `--search TEXT`
- `--visibility hidden_transactions_only|all_transactions`
- `--has-attachments/--no-has-attachments`
- `--has-notes/--no-has-notes`
- `--hidden-from-reports/--no-hidden-from-reports`
- `--split/--no-split`
- `--recurring/--no-recurring`
- `--pending/--no-pending`
- `--imported-from-mint/--no-imported-from-mint`
- `--synced-from-institution/--no-synced-from-institution`
- `--needs-review/--no-needs-review`
- Shared output options
- `--ndjson`
- `--raw`

Omitting a paired boolean option applies no filter.

```bash
monarch transactions list \
  --preset this-month \
  --search "coffee" \
  --no-pending \
  --has-notes \
  --needs-review \
  --limit 200 \
  --json
```

For pipelines:

```bash
monarch --quiet transactions list --search "Coffee" | \
  monarch --allow-mutations transactions batch-update \
    --stdin \
    --category CAT_ID
```

### `transactions get TXN_ID`

Shows normalized detail for one transaction. Pending IDs are redirected to a
posted replacement by default; `--strict` disables that behavior.

Options:

- `--strict`
- Shared output options
- `--raw`

```bash
monarch transactions get TXN_ID --strict --json
```

### `transactions summary`

Shows the all-time transaction aggregate. It intentionally accepts no date or
list filters.

Options:

- Shared output options
- `--raw`

```bash
monarch transactions summary --json
```

### `transactions recurring`

Shows recurring activity for the current month or a selected complete date
range.

Options:

- `-s, --start YYYY-MM-DD`
- `-e, --end YYYY-MM-DD`
- `-p, --preset PRESET`
- Shared output options
- `--raw`

```bash
monarch transactions recurring --preset this-month --json
monarch transactions recurring \
  --start 2024-01-01 \
  --end 2024-12-31 \
  --format table
```

### `transactions update`

Updates one transaction. This is a remote mutation.

Options:

- Required `--transaction-id TXN_ID`
- `--amount AMOUNT`
- `--description TEXT`
- `--category CAT_ID`
- `--notes TEXT`
- `--date YYYY-MM-DD`
- `--dry-run`

At least one change option is required.

```bash
monarch transactions update \
  --transaction-id TXN_ID \
  --category CAT_ID \
  --dry-run

monarch --allow-mutations transactions update \
  --transaction-id TXN_ID \
  --notes "Business expense"
```

### `transactions batch-update`

Applies the same category or notes change to multiple transactions in parallel.
IDs may be supplied explicitly, through stdin, or both. They are deduplicated
in first-seen order.

Options:

- `--transaction-id TXN_ID` — repeatable
- `--stdin`
- `-c, --category CAT_ID`
- `-n, --notes TEXT`
- `--max-concurrency 1..16` — default `4`
- `--dry-run`

```bash
monarch --allow-mutations transactions batch-update \
  --transaction-id TXN1 \
  --transaction-id TXN2 \
  --category CAT_ID \
  --max-concurrency 8
```

### `transactions create`

Creates one manual transaction. This is a remote mutation and requires the
global `--allow-mutations` option before the command path.

Required options:

- `--date YYYY-MM-DD`
- `--account-id ACCOUNT_ID`
- `--amount AMOUNT` — finite number
- `--merchant MERCHANT` — non-empty after trimming
- `--category-id CATEGORY_ID`

Other options:

- `--notes TEXT`
- `--dry-run`

Create is not idempotent. After the write, the CLI reads the returned
transaction ID back without a pending-ID redirect and verifies the requested
date, amount, account, category, merchant, and notes where the released detail
response exposes them. A missing ID, lost response, or verification mismatch is
reported as `ambiguous` (exit `4`) with verification guidance and is never
retried automatically. This version does not expose tags, dedupe/upsert,
duplicate detection, batch operations, `--update-balance`, attachments, or
account/category management.

```bash
monarch --allow-mutations transactions create \
  --date 2026-01-15 \
  --account-id ACC_ID \
  --amount 12.34 \
  --merchant "Coffee Shop" \
  --category-id CAT_ID

monarch transactions create \
  --date 2026-01-15 \
  --account-id ACC_ID \
  --amount 12.34 \
  --merchant "Coffee Shop" \
  --category-id CAT_ID \
  --dry-run
```

### `transactions delete`

Deletes one manual transaction. This is a remote mutation and requires the
global `--allow-mutations` option before the command path. The target is a
required `--transaction-id` option; bulk IDs are never accepted.

Options:

- Required `--transaction-id TXN_ID`
- `--dry-run`

Delete is destructive and prompts for confirmation unless `--yes` is given
after `--allow-mutations`; `--yes` never authorizes the write. The CLI reads
the exact target before deletion and verifies absence afterwards where the
released read capability supports it. Delete is not recoverable, so a lost or
contradictory result is reported as `ambiguous` (exit `4`), never as a claimed
deletion.

```bash
monarch --allow-mutations --yes transactions delete --transaction-id TXN_ID
monarch transactions delete --transaction-id TXN_ID --dry-run
```

## Transaction splits

### `transactions splits show TXN_ID`

Shows the parent amount and current split rows.

Options:

- Shared output options
- `--raw`

```bash
monarch transactions splits show TXN_ID --json
```

### `transactions splits replace`

Replaces the complete split set. Exactly one bounded JSON source is required.

Options:

- Required `--transaction-id TXN_ID`
- `--splits-json JSON_ARRAY`
- `--splits-file PATH`
- `--dry-run`

Replacement arrays contain 1–100 rows. Each row must contain exactly
`merchantName`, `amount`, and `categoryId`; amounts must total the signed
parent transaction amount.

```bash
monarch transactions splits replace \
  --transaction-id TXN_ID \
  --splits-json \
  '[{"merchantName":"Store","amount":-25.00,"categoryId":"CAT_ID"}]' \
  --dry-run

monarch --allow-mutations --yes transactions splits replace \
  --transaction-id TXN_ID \
  --splits-file ./splits.json
```

### `transactions splits clear`

Sends the canonical empty split list.

Options:

- Required `--transaction-id TXN_ID`
- `--dry-run`

```bash
monarch --allow-mutations --yes transactions splits clear \
  --transaction-id TXN_ID
```

## Transaction tags

### `transactions tags list`

Lists all household transaction tags.

Options:

- Shared output options
- `--raw`

```bash
monarch transactions tags list --json
```

### `transactions tags show TXN_ID`

Shows tags assigned to one transaction.

Options:

- Shared output options
- `--raw`

```bash
monarch transactions tags show TXN_ID --json
```

### `transactions tags create`

Creates a reusable household tag.

Options:

- `--name NAME`
- `--color '#RRGGBB'`

```bash
monarch --allow-mutations transactions tags create \
  --name "Travel" \
  --color '#1E90FF'
```

### `transactions tags replace`

Replaces the complete tag set for one transaction.

Options:

- Required `--transaction-id TXN_ID`
- `--tag-id TAG_ID` — repeatable
- `--tag-name NAME` — repeatable, exact and case-sensitive
- `--dry-run`

```bash
monarch transactions tags replace \
  --transaction-id TXN_ID \
  --tag-name "Travel" \
  --dry-run

monarch --allow-mutations --yes transactions tags replace \
  --transaction-id TXN_ID \
  --tag-id TAG_ID \
  --tag-name "Travel"
```

### `transactions tags add`

Adds tags while preserving existing tags. This is a read-modify-write
operation; it is not atomic against concurrent changes.

Options:

- Required `--transaction-id TXN_ID`
- `--tag-id TAG_ID` — repeatable
- `--tag-name NAME` — repeatable, exact and case-sensitive
- `--dry-run`

```bash
monarch --allow-mutations transactions tags add \
  --transaction-id TXN_ID \
  --tag-name "Travel"
```

Already-present tags are skipped and an already-satisfied request is a
successful no-op.

### `transactions tags clear`

Clears every tag from one transaction.

Options:

- Required `--transaction-id TXN_ID`
- `--dry-run`

```bash
monarch --allow-mutations --yes transactions tags clear \
  --transaction-id TXN_ID
```

## Transaction attachments

### `transactions attachments add`

Attaches one supported local file to one explicitly identified transaction as a
three-stage remote workflow: acquire transaction-specific signed upload
parameters, upload the file through the credential-safe media transport
(`mc-sr92`), then register the attachment. The command never calls the upstream
`upload_attachment` helper or any upstream private upload method; it consumes
only the reviewed adapter boundary.

Options:

- Required `--transaction-id TXN_ID`
- Required `--file PATH`
- `--filename NAME` — optional remote filename override, validated by the same
  policy as the derived basename
- `--dry-run`

Local file policy (v1): supported extensions are `.pdf`, `.jpg`, `.jpeg`,
`.png`, `.gif`, and `.webp`; the maximum size is 10 MiB; filenames are limited
to 255 characters and reject path separators and control characters. Execution
opens the file once with `O_NOFOLLOW`, validates the open descriptor as a
regular, readable, non-empty file under the size cap, and reads from that same
descriptor. Symbolic links, directories, empty files, over-limit files, and
unsupported or content-mismatched files are rejected before authentication or
any remote operation. Extension/MIME checks are local policy only and do not
guarantee that the remote service accepts the file.

The dry-run preview is fully offline: it validates local metadata (existence,
regular file, filename policy, size) without reading file contents and performs
no authentication lookup, transaction read, signed-parameter request, or upload.
It reports only the target transaction ID, the sanitized remote basename, the
local size, and the locally inferred content type.

The requested transaction is verified by an exact, non-redirecting detail read
before any upload. The media and registration stages are each attempted exactly
once. A media upload that succeeds but whose registration fails or is
unconfirmed is reported as a partial `mutation-outcome.v1` result (exit `4`)
with the orphaned media asset acknowledged; no cleanup or rollback is claimed,
and filename/size matching is never used to identify or deduplicate
attachments.

```bash
monarch transactions attachments add \
  --transaction-id TXN_ID \
  --file ./receipt.pdf \
  --dry-run

monarch --allow-mutations transactions attachments add \
  --transaction-id TXN_ID \
  --file /path/to/scan.png \
  --filename "receipt.png"
```

Receipt-inbox upload and follow-up transaction edits (including `--notes`
convenience updates) are out of scope.

## Transaction review state

The upstream `reviewed` and `needsReview` inputs are not interchangeable, so the
CLI exposes two explicit, intent-oriented operations. Users never supply a pair
of review booleans:

- `transactions review mark` sends `reviewed=True` and omits `needsReview`;
- `transactions review return` sends `needsReview=True` and omits `reviewed`.

`reviewed=False` and `needsReview=False` are never sent by this surface. Each
command targets exactly one transaction through a required `--transaction-id`
option (never a positional argument).

### `transactions review mark`

Marks one transaction reviewed.

Options:

- Required `--transaction-id TXN_ID`
- `--dry-run`

```bash
monarch --allow-mutations transactions review mark --transaction-id TXN_ID
monarch transactions review mark --transaction-id TXN_ID --dry-run
```

### `transactions review return`

Returns one transaction to the review queue.

Options:

- Required `--transaction-id TXN_ID`
- `--dry-run`

```bash
monarch --allow-mutations transactions review return --transaction-id TXN_ID
```

Both operations read the transaction detail first (without a pending-ID
redirect) to verify exact identity and to report a deterministic no-op when the
requested state is already observed. After writing, the detail is read again to
confirm the intended review state and that category and merchant identity were
unchanged. The serialized mutation input contains only the transaction ID and
the one intended review-state field; unrelated fields such as `category`,
`name`, `amount`, `date`, `notes`, and `goalId` are never sent. The stable
output reports the observed `needs_review`, `reviewed_at`, and
`reviewed_by_user` fields and never invents a `reviewed` boolean.

## Mutation behavior

Remote mutations are:

- `accounts refresh`
- `transactions update`
- `transactions batch-update`
- `transactions create`
- `transactions delete`
- `transactions tags create`, `replace`, `add`, and `clear`
- `transactions splits replace` and `clear`
- `transactions attachments add`
- `transactions review mark` and `transactions review return`

All require `--allow-mutations` after validation, except dry-run previews.
`--yes` is needed only to skip confirmation for destructive tag and split
operations. Remote mutations make one attempt; read retries never apply to
writes.

After a write is attempted, the CLI emits `mutation-outcome.v1` on stdout.
Ambiguous and partial outcomes exit `4`; never retry those blindly. See
[Mutation outcomes](mutation-outcomes.md) for the full contract.
