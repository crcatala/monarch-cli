# Output contracts

Monarch CLI separates normalized output for users and scripts from explicit
raw passthrough for callers that need the upstream response.

## Output formats

| Format | Behavior |
|---|---|
| `plain` | Human-readable terminal output |
| `json` | Pretty-printed JSON |
| `table` | Rich table output for list-shaped records |
| `csv` | CSV for list-shaped records |
| `compact` | Single-line JSON |
| `ndjson` | One JSON record per line; accounts and transaction lists only |

On a TTY, the default is plain output. When stdout is piped or redirected, the
default is JSON. Use `--json` or `--format` to select explicitly.

For commands with a concise display selection, `plain`, `table`, and `compact`
show a curated subset. JSON, CSV, and NDJSON retain complete normalized
records. `--raw` bypasses normalization where supported.

Global output options must appear before the command path:

```bash
monarch --json accounts list
monarch --quiet transactions list --preset this-month
```

## Quiet output

`--quiet` prints an extractable `id` for each returned record, one per line.
It is intended for pipelines such as:

```bash
monarch --quiet transactions list --search "Coffee" |
  monarch --allow-mutations transactions batch-update \
    --stdin --category CAT_ID
```

If a returned record has no extractable ID, quiet mode fails instead of silently
emitting an incomplete result. Mutations and dry-run previews cannot use quiet
mode.

## Normalized versus raw output

Normalized output uses stable CLI field names, tolerates missing optional
upstream fields, and preserves unavailable values as `null` rather than
inventing financial values. `--raw` returns the upstream structure, including
unknown fields and null containers, where the command supports it.

The stable normalized records below are also published as checked-in JSON
Schema Draft 2020-12 artifacts packaged with the CLI. See
[Machine-readable output schemas](schema-contracts.md) for the contract URNs,
the module-level mapping that resolves them, validation examples, and the
compatibility policy. Raw passthrough is explicitly unschematized and unstable.

Raw mode is not identical for every command:

- Most commands return the upstream response directly.
- `investments holdings --raw` returns a deterministic account-ID-keyed CLI
envelope containing each account's untouched holdings response.
- Some commands reject raw mode together with options that only shape
  normalized output, such as `institutions list --include-deleted` and
  `investments holdings --aggregate`.

## Stable normalized records

The following are the principal normalized contracts. Fields are additive only;
missing values remain `null` unless noted otherwise.

### Accounts

`accounts list` records contain:

```text
id, name, type, subtype, balance, institution,
is_active, is_manual, owner_id, owner_name,
type_name, subtype_name, is_asset,
credit_limit, provider_credit_limit, apr, interest_rate,
minimum_payment, planned_payment, excluded_from_debt_paydown,
last_updated
```

`accounts types` returns `group`, `type`, `type_display`, `subtype`, and
`subtype_display` records. Other account read shapes are:

- `history`: `date`, `balance`, `account_id`, `account_name`
- `recent-balances`: `id`, `recent_balances` with `date` and `balance`
- `snapshots`: `date`, `balance`
- `snapshots-by-type`: `snapshots` and `account_types`; snapshot rows contain
  `account_type`, `period`, and `balance`
- `refresh-status`: synchronization status, completion state, requested IDs,
  known IDs, unknown IDs, and checked count

### Transactions

Transaction list records contain:

```text
id, date, amount, description, category, category_id,
account, account_id, is_pending, needs_review, review_status,
owner_id, owner_name, ownership_overridden_at, notes
```

`description` is selected deterministically from merchant name, Plaid name,
or `null`. `is_pending` and `needs_review` are booleans; other unavailable
values remain nullable.

Transaction detail additionally exposes requested/returned identity, redirect
state, original transaction information, recurring/report visibility flags,
manual state, attachments, tags, and split information.

`transactions summary` is an all-time aggregate with:

```text
count, average, maximum, maximum_expense, net_sum,
income, expenses, first, last
```

`transactions recurring` returns normalized stream, merchant, account,
category, expected/observed amounts and dates, amount differences, state flags,
and linked transaction IDs.

### Budgets, categories, and cashflow

Budget records contain:

```text
category_id, budgeted, spent, remaining
```

Category records contain:

```text
id, name, group, icon
```

Cashflow summary contains:

```text
income, expenses, savings, savings_rate
```

Cashflow detail contains `categories`, `category_groups`, `merchants`, and the
same `summary` shape. Category and group amounts preserve signed upstream
aggregates; merchant expenses are positive.

### Institutions and subscriptions

Institution records contain credential and connection fields:

```text
credential_id, provider, institution_id, institution_name,
update_required, disconnected, disconnected_at, last_updated,
issue, balance_status, transaction_status, accounts
```

Associated accounts contain `id`, `name`, `subtype`, `mask`, `is_deleted`, and
`deleted_at`.

`subscription show` is the normalized subscription contract:

```text
available, is_on_free_trial, has_premium_entitlement
```

Payment-source and referral metadata are excluded from normalized output and
available only through explicit `--raw`.

### Investment holdings

Normalized holdings contain:

```text
account_id, account_name, security_id, holding_id,
ticker, name, security_type, security_type_display,
quantity, basis, price, total_value, last_synced_at
```

`--aggregate` groups rows by non-null security ID. It does not invent currency
conversions or aggregate monetary values where the upstream response does not
provide verifiable currency metadata. See
[Investment holdings](investment-holdings.md) for details.

## Mutation output

After a remote write is attempted, the CLI emits the versioned
`mutation-outcome.v1` JSON envelope on stdout. It includes the operation,
overall status, ordered item results, sanitized errors, and verification guidance
when the outcome is ambiguous.

Pre-execution validation and authorization failures remain structured errors on
stderr. Dry-run previews use JSON with `status: "dry_run"` but are deliberately
not mutation outcomes.

See [Mutation outcomes](mutation-outcomes.md) for statuses, exit codes, retry
behavior, and safe recovery from ambiguous writes.
